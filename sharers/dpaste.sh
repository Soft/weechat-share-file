#!/usr/bin/env bash

FILE="$1"

declare -a DEPS
DEPS=( curl )

declare -A TYPES
TYPES=([c]=c \
       [clj]=clojure \
       [css]=css \
       [go]=go \
       [hs]=haskell \
       [htm]=html \
       [html]=html \
       [ini]=ini \
       [java]=java \
       [js]=js \
       [lua]=lua
       [php]=php \
       [pl]=perl \
       [rs]=rust \
       [scm]=scheme \
       [sh]=bash \
       [sql]=sql \
       [tex]=tex \
       [xml]=xml \
       [py]=python)

if [[ ! -r "$FILE" ]]; then
    echo "\"$FILE\" does not exist" >&2
    exit 1
fi

function check-deps() {
    for prog in "${DEPS[@]}"; do
        hash "$prog" &>/dev/null
        if [[ $? -ne 0 ]]; then
            echo "$prog is required" >&2
            exit 1
        fi
    done
}

# Default to python like the web interface does
function language() {
    local extension="${1##*.}"
    if [[ "$extension" == "$1" ]]; then
        echo "python"
    else
        echo "${TYPES[$extension]:-python}"
    fi
}

function upload() {
    local lexer="${1}"
    local url="https://dpaste.de/api/"
    local name="$(basename \"$2\")"
    curl -F "content=<${2}" \
         -F "lexer=${lexer}" \
         -F "format=url" \
         -F "filename=\"${name}\"" \
         "$url" \
         2>/dev/null
}

check-deps
LANGUAGE=$(language "$FILE")
upload "$LANGUAGE" "$FILE"
