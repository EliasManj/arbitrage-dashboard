# League identifiers
LIGA_MX = "liga_mx"
PREMIER_LEAGUE = "premier_league"
LA_LIGA = "la_liga"
SERIE_A = "serie_a"
BUNSEDLIGA = "bundesliga"
MLS = "mls"
CHAMPIONS_LEAGUE = "champions_league"
LIGUE_1 = "ligue_1"
ARGENTINA_1 = "argentina_primera"
EREDIVISIE = "eredivisie"
BRASIL_A = "brasil_a"
NFL = "nfl"
MLB = "mlb"

# Sport identifiers
SPORT_FOOTBALL = "football"
SPORT_AMERICAN_FOOTBALL = "american_football"
SPORT_BASEBALL = "baseball"

# League → sport mapping (authoritative source of truth)
LEAGUE_SPORT: dict[str, str] = {
    LIGA_MX: SPORT_FOOTBALL,
    PREMIER_LEAGUE: SPORT_FOOTBALL,
    LA_LIGA: SPORT_FOOTBALL,
    SERIE_A: SPORT_FOOTBALL,
    BUNSEDLIGA: SPORT_FOOTBALL,
    MLS: SPORT_FOOTBALL,
    CHAMPIONS_LEAGUE: SPORT_FOOTBALL,
    LIGUE_1: SPORT_FOOTBALL,
    ARGENTINA_1: SPORT_FOOTBALL,
    EREDIVISIE: SPORT_FOOTBALL,
    BRASIL_A: SPORT_FOOTBALL,
    NFL: SPORT_AMERICAN_FOOTBALL,
    MLB: SPORT_BASEBALL,
}

# Market types
MARKET_1X2 = "1x2"
MARKET_MONEYLINE = "moneyline"
MARKET_TOTAL = "total"
MARKET_BTTS = "btts"
MARKET_DOUBLE_CHANCE = "double_chance"
MARKET_ASIAN_HANDICAP = "asian_handicap"

# 1x2 outcomes
HOME = "home"
DRAW = "draw"
AWAY = "away"

# Total outcomes
OVER = "over"
UNDER = "under"

# BTTS outcomes
YES = "yes"
NO = "no"

# Double Chance outcomes
HOME_OR_DRAW = "home_or_draw"
HOME_OR_AWAY = "home_or_away"
DRAW_OR_AWAY = "draw_or_away"
