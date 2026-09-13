"""Create a dedicated local Devnet wallet; optionally request free faucet SOL."""
import argparse
import json
from forensic_auditor import integrity as chain
from solders.keypair import Keypair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--airdrop', action='store_true', help='Request 1 free Devnet SOL (faucet limits apply)')
    args = parser.parse_args()
    chain.KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not chain.KEY_PATH.exists():
        with chain.KEY_PATH.open('x') as file:
            json.dump(list(bytes(Keypair())), file)
    public = str(chain.wallet().pubkey())
    print(f'Dedicated Devnet public address: {public}')
    print('Keep tmp/solana-devnet-keypair.json private and backed up; never fund it on Mainnet.')
    try:
        chain.check_network()
        if args.airdrop:
            signature = chain.rpc('requestAirdrop', [public, 1_000_000_000])
            print(f'Airdrop requested: {signature}')
        balance = chain.rpc('getBalance', [public, {'commitment': 'confirmed'}])['value']
        print(f'Devnet balance: {balance} lamports')
    except chain.IntegrityError as error:
        print(str(error))
        print(f'If the RPC faucet is limited, use https://faucet.solana.com with public address {public}.')


if __name__ == '__main__':
    main()
