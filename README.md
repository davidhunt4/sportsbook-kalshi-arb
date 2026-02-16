# Kalshi Trading Bot

1. Fetch NBA game markets from Kalshi
2. Fetch odds from Pinnacle (via The Odds API)
3. Calculates expected value by comparing Pinnacle's true odds vs Kalshi's prices
4. Executes buy orders on Kalshi for opportunities with >2.5% EV
5. Sends trade notifications via AWS SNS (optional)

Next step is to sell once Kalshi adjusts to the sportsbook-implied odds. Also to stop getting rate limited for the sportsbook API.

## Setup Instructions

### Prerequisites

- Python 3.7 or higher
- pip (Python package manager)
- Git
- A Kalshi API account with API credentials
- (Optional) AWS account if using SNS notifications

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Or if you prefer using a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set Up Credentials

#### Create Private Key File

1. Obtain your private key from Kalshi
2. Create a file named `demo_private_key.pem` in the project root directory
3. Paste your private key content into this file

**Important:** The `.pem` file is already in `.gitignore` and will not be committed to version control.

#### Configure Environment Variables

Create a `.env` file with the following content:

```bash
# Required API Keys
KALSHI_DEMO_API_KEY=your_kalshi_api_key_here
PINNACLE_API_KEY=your_pinnacle_api_key_here

# Optional - AWS SNS for trade notifications
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:123456789012:your-topic-name
```

**Note:** The `.env` file is already in `.gitignore` and will not be committed to version control.

#### AWS Credentials (for SNS notifications)

**For Lambda deployment:** Attach an IAM role to your Lambda function with SNS publish permissions. No explicit credentials needed.

**For local development:** Configure AWS CLI:
```bash
aws configure
```
This stores credentials in `~/.aws/credentials`. The boto3 client automatically uses these credentials.

### 4. Running the Scripts

You can either run the bot locally or deploy it to AWS Lambda.

#### Option A: Run Locally

Uncomment the code at the bottom of `full_test_script.py` and run:

```bash
python full_test_script.py
```

#### Option B: Deploy to AWS Lambda

**Prerequisites:**
- AWS account
- AWS CLI installed and configured: `aws configure`

**Step 1: Create an IAM Role for Lambda**

1. Go to AWS Console → IAM → Roles → Create role
2. Select "Lambda" as the trusted entity
3. Attach policies:
   - `AWSLambdaBasicExecutionRole` (for CloudWatch logs)
   - `AmazonSNSFullAccess` (or create custom policy with SNS publish permissions)
4. Name it (e.g., `kalshi-lambda-role`) and create

**Step 2: Create the Lambda Function**

Via AWS Console:
1. Go to AWS Lambda → Create function
2. Choose "Author from scratch"
3. Function name: `kalshi-trading-bot` (or match name in update_lambda.sh)
4. Runtime: Python 3.11
5. Architecture: x86_64
6. Execution role: Use the role you created above
7. Create function

**Step 3: Configure the Lambda Function**

1. **Set environment variables:**
   - `KALSHI_DEMO_API_KEY` = your Kalshi API key
   - `PINNACLE_API_KEY` = your Pinnacle API key
   - `SNS_TOPIC_ARN` = your SNS topic ARN

2. **Configure settings:**
   - Handler: `full_test_script.lambda_handler`
   - Timeout: 30 seconds (or more)
   - Memory: 512 MB (or more)

**Step 4: Deploy your code**

1. **Set up the package directory:**
   ```bash
   # Install dependencies into package directory
   pip install -r requirements.txt -t package/
   
   # Copy your private key
   cp demo_private_key.pem package/
   ```

2. **Deploy using the provided script:**
   ```bash
   chmod +x update_lambda.sh
   ./update_lambda.sh
   ```
   
   **Note:** This script assumes your function is named `kalshi-trading-bot`. If you used a different name, edit the function name in `update_lambda.sh`.

**Step 5: Test the function**

In AWS Console, create a test event (empty JSON `{}`) and invoke the function to verify it works.

**Subsequent Updates:**

After initial setup, just run `./update_lambda.sh` to deploy code changes.

## Project Structure

```
.
├── full_test_script.py      # Main trading script with Lambda handler
├── kalshi_utils.py          # Kalshi API utilities
├── pinnacle_utils.py        # Pinnacle API utilities
├── requirements.txt         # Python dependencies
├── update_lambda.sh         # AWS Lambda deployment script
├── demo_private_key.pem     # Your Kalshi private key (not in repo)
├── .env                     # Environment variables (not in repo)
└── package/                 # Lambda deployment package with dependencies
```
