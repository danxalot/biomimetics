# Cloud Infrastructure Scripts

## Vultr Free Tier Provisioning

Automated VPS provisioning for the free tier.

### Requirements

```bash
pip install httpx
```

### Usage

```bash
# Set API key
export VULTR_API_KEY="your_api_key_here"

# Run provisioner
python3 vultr_provision.py

# Or provide API key via argument
python3 vultr_provision.py --api-key your_api_key_here
```

### Features

- ✅ Free tier plan: vc2-1c-0.5gb-free
- ✅ Region: London (lhr) or closest EU
- ✅ OS: Debian 12 (bookworm)
- ✅ Backups: Disabled (no hidden charges)
- ✅ Cloud-init script injection
- ✅ Interactive confirmation
