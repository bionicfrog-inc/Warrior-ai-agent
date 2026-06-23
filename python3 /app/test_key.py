cat > /app/test_key.py << 'EOF'
import requests, os
key = os.environ.get('ANTHROPIC_KEY','')
print(f'Key length: {len(key)}')
r = requests.post('https://api.anthropic.com/v1/messages',
  headers={'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
  json={'model':'claude-haiku-4-5-20251001','max_tokens':10,'messages':[{'role':'user','content':'hi'}]},
  timeout=10)
print(r.status_code, r.text[:300])
EOF
python3 /app/test_key.py
