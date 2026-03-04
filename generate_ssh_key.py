import subprocess
import os

ssh_dir = os.path.expanduser("~/.ssh")
os.makedirs(ssh_dir, exist_ok=True)

key_path = os.path.join(ssh_dir, "id_ed25519")

# Remove old key if exists
if os.path.exists(key_path):
    os.remove(key_path)
if os.path.exists(key_path + ".pub"):
    os.remove(key_path + ".pub")

# Generate SSH key without passphrase using os.system (non-blocking)
cmd = f'ssh-keygen -t ed25519 -C "your.email@example.com" -f "{key_path}" -N "" -q'
os.system(cmd)

import time
time.sleep(2)

# Display public key
pub_key_path = key_path + ".pub"
if os.path.exists(pub_key_path):
    with open(pub_key_path, 'r') as f:
        pub_key = f.read().strip()
        print("\n=== YOUR NEW PUBLIC KEY (Copy this to GitHub) ===")
        print(pub_key)
        print("=" * 60)
        print("\nKey saved to:", key_path)
else:
    print("Public key not found! Check if ssh-keygen is installed.")
