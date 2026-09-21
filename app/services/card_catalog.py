POPULAR_CARD_CATALOG: dict[str, str] = {
    "rbc_visa_platinum": "RBC Visa Platinum",
    "rbc_avion_visa_infinite": "RBC Avion Visa Infinite",
    "td_cash_back_visa_infinite": "TD Cash Back Visa Infinite",
    "td_rewards_visa": "TD Rewards Visa",
    "cibc_dividend_visa": "CIBC Dividend Visa",
    "bmo_cashback_mastercard": "BMO CashBack Mastercard",
    "scotiabank_momentum_visa": "Scotia Momentum Visa",
    "national_bank_world_mastercard": "National Bank World Mastercard",
    "capital_one_guaranteed_mastercard": "Capital One Guaranteed Mastercard",
    "other": "Autre",
}


def resolve_card_name(*, selection_type: str, popular_card_key: str | None, custom_card_name: str | None) -> str:
    if selection_type == "popular":
        if not popular_card_key:
            raise ValueError("popularCardKey is required when selectionType=popular")
        name = POPULAR_CARD_CATALOG.get(popular_card_key)
        if not name:
            raise ValueError("Unknown popularCardKey")
        return name

    if selection_type == "other":
        if not custom_card_name or not custom_card_name.strip():
            raise ValueError("customCardName is required when selectionType=other")
        return custom_card_name.strip()

    raise ValueError("selectionType must be popular or other")
