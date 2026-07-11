#!/usr/bin/env bash
# Claude Code Status Line
# Zeigt: Context-Auslastung, 5h-Rate-Limit, Wochen-Rate-Limit (je mit Reset-Countdown)

input=$(cat)

# ── ANSI-Farben ──────────────────────────────────────────────────────────────
RESET="\033[0m"
BOLD="\033[1m"

GREEN="\033[38;5;78m"
YELLOW="\033[38;5;220m"
ORANGE="\033[38;5;208m"
RED="\033[38;5;196m"
CYAN="\033[38;5;117m"
BLUE="\033[38;5;69m"
PURPLE="\033[38;5;141m"
WHITE="\033[38;5;252m"
GRAY="\033[38;5;240m"

# ── Progressbar ───────────────────────────────────────────────────────────────
render_bar() {
    local pct=$1 width=$2 filled_char=$3 empty_char=$4 color=$5
    local filled=$(( pct * width / 100 ))
    local empty=$(( width - filled ))
    local bar="" i
    for (( i=0; i<filled; i++ )); do bar="${bar}${filled_char}"; done
    for (( i=0; i<empty; i++ )); do bar="${bar}${empty_char}"; done
    printf "${color}${bar}${RESET}"
}

# ── Farbe je nach Auslastung ─────────────────────────────────────────────────
usage_color() {
    local pct=$1
    if   (( pct < 40 )); then printf "%s" "$GREEN"
    elif (( pct < 70 )); then printf "%s" "$YELLOW"
    elif (( pct < 85 )); then printf "%s" "$ORANGE"
    else                      printf "%s" "$RED"
    fi
}

# ── Reset-Countdown aus Unix-Timestamp ───────────────────────────────────────
# Gibt "Xh Ym" oder "Ym" oder "jetzt" zurück
reset_countdown() {
    local resets_at=$1
    if [ -z "$resets_at" ] || [ "$resets_at" = "null" ]; then
        printf "?"
        return
    fi
    local now remaining
    now=$(date +%s)
    remaining=$(( resets_at - now ))
    if (( remaining <= 0 )); then
        printf "jetzt"
    elif (( remaining < 3600 )); then
        printf "%dm" $(( remaining / 60 ))
    else
        local h=$(( remaining / 3600 ))
        local m=$(( (remaining % 3600) / 60 ))
        if (( m == 0 )); then
            printf "%dh" "$h"
        else
            printf "%dh%dm" "$h" "$m"
        fi
    fi
}

# ── 1. Context-Window ─────────────────────────────────────────────────────────
ctx_pct=$(echo "$input" | jq -r '.context_window.used_percentage // 0')
ctx_pct_int=$(printf "%.0f" "$ctx_pct")
ctx_clr=$(usage_color "$ctx_pct_int")

# ── 2. 5h-Rate-Limit ─────────────────────────────────────────────────────────
h5_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
h5_resets=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')

if [ -z "$h5_pct" ]; then
    h5_pct_int=0
    h5_label="–"
else
    h5_pct_int=$(printf "%.0f" "$h5_pct")
    h5_label="↺ $(reset_countdown "$h5_resets")"
fi
h5_clr=$(usage_color "$h5_pct_int")

# ── 3. 7-Tage-Rate-Limit ─────────────────────────────────────────────────────
w7_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
w7_resets=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')

if [ -z "$w7_pct" ]; then
    w7_pct_int=0
    w7_label="–"
else
    w7_pct_int=$(printf "%.0f" "$w7_pct")
    w7_label="↺ $(reset_countdown "$w7_resets")"
fi
w7_clr=$(usage_color "$w7_pct_int")

# ── Ausgabe ───────────────────────────────────────────────────────────────────
SEP="${GRAY} · ${RESET}"
BAR_WIDTH=8
LBL="${WHITE}${BOLD}"

ctx_bar=$(render_bar "$ctx_pct_int" $BAR_WIDTH "█" "░" "$ctx_clr")
h5_bar=$(render_bar  "$h5_pct_int"  $BAR_WIDTH "█" "░" "$h5_clr")
w7_bar=$(render_bar  "$w7_pct_int"  $BAR_WIDTH "█" "░" "$w7_clr")

printf "${LBL}ctx${RESET} ${ctx_bar} ${ctx_clr}${ctx_pct_int}%%${RESET}"
printf "${SEP}"
printf "${LBL}5h${RESET}  ${h5_bar} ${h5_clr}${h5_pct_int}%%${RESET} ${GRAY}${h5_label}${RESET}"
printf "${SEP}"
printf "${LBL}week${RESET} ${w7_bar} ${w7_clr}${w7_pct_int}%%${RESET} ${GRAY}${w7_label}${RESET}"
printf "\n"
