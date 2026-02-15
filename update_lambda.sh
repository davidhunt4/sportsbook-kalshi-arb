#!/bin/bash

# Copy updated code to package
cp full_test_script.py package/
cp kalshi_utils.py package/
cp pinnacle_utils.py package/

# Repackage
cd package
zip -r ../lambda_deployment.zip .
cd ..

# Upload to Lambda
aws lambda update-function-code \
  --function-name kalshi-trading-bot \
  --zip-file fileb://lambda_deployment.zip

echo "Lambda updated!"

# Test it
# aws lambda invoke --function-name kalshi-trading-bot output.json
# cat output.json