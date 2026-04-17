def normalize_wallet_type(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""

    normalized = raw.lower().replace(" ", "").replace("-", "").replace("_", "")

    if normalized in {
        "metamask",
        "metamasksdk",
        "io.metamask",
        "io.metamask.mobile",
        "iometamask",
        "iometamaskmobile",
    }:
        return "MetaMask"

    if normalized in {"rabby", "io.rabby", "iorabby"}:
        return "Rabby"

    if normalized in {"trustwallet", "trust", "com.trustwallet.app", "comtrustwalletapp"}:
        return "Trust Wallet"

    if normalized in {"walletconnect"}:
        return "WalletConnect"

    return raw
