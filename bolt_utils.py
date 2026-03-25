import asyncio
import websockets
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

class BoltOddsManager:
    """
    Manages Bolt websocket connection and tracks current state of NBA games across sportsbooks.
    """
    
    def __init__(self, api_key: str, sportsbooks: List[str]):
        """
        Initialize Bolt odds manager.
        
        Args:
            api_key: Bolt API key
            sportsbooks: List of sportsbook names to subscribe to
        """
        self.api_key = api_key
        self.sportsbooks = sportsbooks
        self.uri = f"wss://spro.agency/api?key={api_key}"
        self.websocket = None
        self.running = False
        
        # Track game states: games[game_id][sportsbook] = full_game_state
        self.games: Dict[str, Dict[str, dict]] = {}
        
    async def connect(self):
        """Establish websocket connection and subscribe to NBA games."""
        self.websocket = await websockets.connect(self.uri, max_size=None)
        ack_message = await self.websocket.recv()
        print(f"Connected to Bolt: {ack_message}")
        
        # Subscribe to NBA Moneyline markets
        subscribe_message = {
            "action": "subscribe",
            "filters": {
                "sports": ["NBA"],
                "sportsbooks": self.sportsbooks,
                "markets": ["Moneyline"]
            }
        }
        
        await self.websocket.send(json.dumps(subscribe_message))
        print(f"Subscribed to NBA Moneyline for sportsbooks: {self.sportsbooks}")
        
    async def _handle_message(self, data: dict):
        """Process incoming websocket message and update internal state."""
        action = data.get('action')
        
        if action == 'ping':
            return
            
        # Extract game identifier
        game_data = data.get('data', {})
        game_id = game_data.get('info', {}).get('universal_id') or game_data.get('info', {}).get('game_id') or game_data.get('game')
        sportsbook = game_data.get('sportsbook')
        
        if not game_id or not sportsbook:
            return
            
        # Initialize game dict if needed
        if game_id not in self.games:
            self.games[game_id] = {}
            
        if action == 'initial_state' or action == 'game_update':
            # Store/update full game state for this sportsbook
            self.games[game_id][sportsbook] = {
                'timestamp': data.get('timestamp', datetime.utcnow().isoformat() + '+00:00'),
                'action': action,
                'data': game_data
            }
            
        elif action == 'line_update':
            # Update specific line in existing game state
            if sportsbook in self.games[game_id]:
                existing_state = self.games[game_id][sportsbook]
                
                # Update the specific outcome
                outcome_name = game_data.get('outcome_name')
                outcome_target = game_data.get('outcome_target')
                
                if outcome_name and outcome_target:
                    outcome_key = f"{outcome_target} {outcome_name}"
                    
                    if 'data' not in existing_state:
                        existing_state['data'] = {}
                    if 'outcomes' not in existing_state['data']:
                        existing_state['data']['outcomes'] = {}
                        
                    existing_state['data']['outcomes'][outcome_key] = {
                        'odds': game_data.get('odds'),
                        'link': game_data.get('link'),
                        'outcome_name': outcome_name,
                        'outcome_line': game_data.get('outcome_line'),
                        'outcome_over_under': game_data.get('outcome_over_under'),
                        'outcome_target': outcome_target
                    }
                    
                existing_state['timestamp'] = data.get('timestamp', datetime.utcnow().isoformat() + '+00:00')
                existing_state['action'] = 'line_update'
                
        elif action == 'game_removed':
            # Remove game for this sportsbook
            if sportsbook in self.games.get(game_id, {}):
                del self.games[game_id][sportsbook]
            # Clean up game_id if no sportsbooks left
            if game_id in self.games and not self.games[game_id]:
                del self.games[game_id]
                
        elif action == 'sport_clear':
            # Remove all games for this sport and sportsbook
            sport = game_data.get('sport')
            if sport == 'NBA':
                for gid in list(self.games.keys()):
                    if sportsbook in self.games[gid]:
                        del self.games[gid][sportsbook]
                    if not self.games[gid]:
                        del self.games[gid]
                        
        elif action == 'book_clear':
            # Remove all games for this sportsbook
            for gid in list(self.games.keys()):
                if sportsbook in self.games[gid]:
                    del self.games[gid][sportsbook]
                if not self.games[gid]:
                    del self.games[gid]
                    
    async def listen(self):
        """Listen for websocket messages and update game states."""
        self.running = True
        
        while self.running:
            try:
                message = await self.websocket.recv()
                msg = json.loads(message)
                
                for data in msg:
                    action = data.get('action')
                    print(f"[WEBSOCKET] {action}: {data.get('data', {}).get('sportsbook', 'N/A')} - {data.get('data', {}).get('game', 'N/A')}")

                for data in msg:
                    await self._handle_message(data)
                    
            except websockets.ConnectionClosed as e:
                print(f"Connection closed: {e}")
                if self.running:
                    print("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
                    await self.connect()
                    
            except Exception as e:
                print(f"Error processing message: {e}")
                
    async def start(self):
        """Start the Bolt odds manager (connect and listen)."""
        await self.connect()
        await self.listen()
        
    async def stop(self):
        """Stop the odds manager."""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            
    def get_bevents(self) -> List[dict]:
        """
        Get the most recent state for each available NBA game/sportsbook combo.
        
        Returns:
            List of game states, each formatted like:
            {
                "timestamp": "2026-03-05T17:48:56.025296+00:00",
                "action": "initial_state",
                "data": {
                    "sport": "NBA",
                    "sportsbook": "draftkings",
                    "game": "Orlando Magic vs Dallas Mavericks, 2026-03-05, 07",
                    "home_team": "Orlando Magic",
                    "away_team": "Dallas Mavericks",
                    "info": {...},
                    "outcomes": {...}
                }
            }
        """
        bevents = []
        
        for game_id, sportsbooks in self.games.items():
            for sportsbook, state in sportsbooks.items():
                bevents.append(state)
                
        return bevents


# Global instance for easy access
_bolt_manager: Optional[BoltOddsManager] = None


async def start_bolt_stream(api_key: Optional[str] = None, sportsbooks: Optional[List[str]] = None):
    """
    Start the Bolt odds stream in the background.
    
    Args:
        api_key: Bolt API key (defaults to BOLT_API_KEY env var)
        sportsbooks: List of sportsbooks to subscribe to (defaults to 10-book weighted list)
    """
    global _bolt_manager
    
    if api_key is None:
        api_key = os.getenv('BOLT_API_KEY')
        
    if sportsbooks is None:
        # Default to the 10 sportsbooks used in correlation analysis
        sportsbooks = [
            "bookmaker", "betonline", "fanduel", "draftkings", "betmgm",
            "espnbet", "thescore", "betrivers", "hardrock", "ballybet"
        ]
        
    _bolt_manager = BoltOddsManager(api_key, sportsbooks)
    
    # Start listening in background
    asyncio.create_task(_bolt_manager.start())
    
    # Give it a moment to establish connection and receive initial state
    await asyncio.sleep(2)
    
    return _bolt_manager


def get_bevents() -> List[dict]:
    """
    Get the current state of all NBA games from Bolt.
    Must call start_bolt_stream() first.
    
    Returns:
        List of game states for each game/sportsbook combination
    """
    global _bolt_manager
    
    if _bolt_manager is None:
        raise RuntimeError("Bolt stream not started. Call start_bolt_stream() first.")
        
    return _bolt_manager.get_bevents()


async def stop_bolt_stream():
    """Stop the Bolt odds stream."""
    global _bolt_manager
    
    if _bolt_manager:
        await _bolt_manager.stop()
        _bolt_manager = None
