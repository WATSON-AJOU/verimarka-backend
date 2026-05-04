WALLET_TYPE_ALIASES = {
    "metamask": "metaMask",
    "meta_mask": "metaMask",
    "meta-mask": "metaMask",
    "rabby": "rabby",
    "trust": "trustWallet",
    "trustwallet": "trustWallet",
    "trust_wallet": "trustWallet",
    "trust-wallet": "trustWallet",
    "walletconnect": "walletConnect",
    "wallet_connect": "walletConnect",
    "wallet-connect": "walletConnect",
}


def normalize_wallet_type(wallet_type: str | None) -> str:
    value = (wallet_type or "").strip()
    if not value:
        return ""

    lookup_key = value.replace(" ", "").lower()
    return WALLET_TYPE_ALIASES.get(lookup_key, value[:50])
