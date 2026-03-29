# Kalshi Trading Bot

A real-time arbitrage trading bot that monitors odds discrepancies between Kalshi and major sportsbooks.

## Overview

The bot:
1. Connects to the **Bolt API stream** for real-time sportsbook odds (multiple books aggregated)
2. Fetches **Kalshi moneyline markets** for NBA, MLB, and NHL games
3. Averages Bolt odds across all connected sportsbooks
4. Identifies arbitrage opportunities when Kalshi odds are >2.5% lower than market average
5. Logs trade opportunities to a CSV file for execution
6. Automatically tracks positions and identifies exit opportunities

Supports multiple sports: **NBA**, **MLB**, **NHL**

## Price Jump Analysis Tool

A new tool has been added to analyze historical price movements in NBA H2H contracts. This tool can:
- Detect all price jumps >2.5% using 1-minute candlestick data
- Track when jumps happen relative to contract launch and game start
- Measure jump duration and volume
- Export data for further analysis

See [PRICE_JUMP_ANALYSIS_README.md](PRICE_JUMP_ANALYSIS_README.md) for detailed documentation.

## Setup Instructions

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- A Kalshi API account with API credentials
- A Bolt API account with API credentials
- EC2 instance or local machine for running the bot

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Or using a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root with:

```bash
# Required API Keys
BOLT_API_KEY=your_bolt_api_key_here
KALSHI_DEMO_API_KEY=your_kalshi_api_key_here

# Optional settings (defaults shown)
TRADE_LOG_PATH=./trade_log.csv
LOOP_INTERVAL_SECONDS=2
WARMUP_SECONDS=10
```

**Note:** The `.env` file is in `.gitignore` and will not be committed.

### 4. Running the Bot

#### Local Execution

```bash
python get_kandb_odds_aws.py
```

The bot will:
- Connect to the Bolt WebSocket stream
- Wait for data to arrive (see `WARMUP_SECONDS`)
- Begin monitoring for arbitrage opportunities
- Log trades to `TRADE_LOG_PATH` (CSV format)

#### EC2 Deployment

See [EC2_QUICK_START.md](ec2stuff/EC2_QUICK_START.md) for detailed instructions on setting up and running on AWS EC2 with systemd service management.

## Project Structure

```
.
├── get_kandb_odds_aws.py    # Main trading bot (Bolt + Kalshi arbitrage)
├── bolt_utils.py            # Bolt API utilities and WebSocket stream
├── kalshi_utils.py          # Kalshi API utilities
├── pinnacle_utils.py        # Pinnacle API utilities (legacy)
├── requirements.txt         # Python dependencies
├── trade_log.csv            # Trade execution log (auto-generated)
├── .env                     # Environment variables (not in repo)
├── jump_data_exploration/   # Price jump analysis tool
└── testing/                 # Test scripts and notebooks
```

## Trade Log Format

The `trade_log.csv` file logs all identified opportunities:

```
Date, Time, Home Team, Away Team, Action, Ticker, Kalshi Price, Bolt Average Price, Sportsbook, Timestamp
2026-03-29, NBA, Boston, Miami, BUY, ..., 0.52, 0.56, average, 2026-03-29T14:32:10.123456
```

Fields:
- **Action**: `BUY` (buy opportunity) or `SELL` (close position)
- **Kalshi Price**: The asking/bidding price on Kalshi
- **Bolt Average Price**: Implied probability from averaged sportsbook odds
- **Sportsbook**: Which book(s) provided the quote or "average"
