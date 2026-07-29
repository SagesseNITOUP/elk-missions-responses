#!/usr/bin/env bash
# Lab 2 — acceptance test. Run once your pipeline has been ingesting for a
# minute or two:   ./scripts/check.sh
# Prints PASS/FAIL per mission. All PASS = ready to submit.
set -uo pipefail

ES="localhost:9200"
pass=0; fail=0

check() {  # check <label> <python-expr over $json>
  local label="$1" url="$2" expr="$3"
  local json
  json=$(curl -s "$ES/$url")
  if python3 - "$expr" <<EOF 2>/dev/null
import json, sys
r = json.loads('''$json''')
sys.exit(0 if eval(sys.argv[1]) else 1)
EOF
  then echo "PASS  $label"; pass=$((pass+1))
  else echo "FAIL  $label"; fail=$((fail+1))
  fi
}

echo "== Lab 2 acceptance =="

check "ES is reachable" "" "'cluster_name' in r or 'name' in r"

# Mission 6 (structure): the three business indices exist and are non-empty
check "M2/M6: shopfast-web-* has documents" \
  "shopfast-web-*/_count" "r.get('count', 0) > 0"
check "M3/M6: shopfast-app-* has documents" \
  "shopfast-app-*/_count" "r.get('count', 0) > 0"
check "M4/M6: shopfast-orders-* has documents" \
  "shopfast-orders-*/_count" "r.get('count', 0) > 0"

# Mission 2: numeric types on web
check "M2: 'status' is numeric in shopfast-web-*" \
  "shopfast-web-*/_mapping/field/status" \
  "any(f.get('mapping', {}).get('status', {}).get('type') in ('long','integer','short')
      for idx in r.values() for f in [idx.get('mappings', {}).get('status', {})])"
check "M2: 'bytes' is numeric in shopfast-web-*" \
  "shopfast-web-*/_mapping/field/bytes" \
  "any(f.get('mapping', {}).get('bytes', {}).get('type') in ('long','integer','short')
      for idx in r.values() for f in [idx.get('mappings', {}).get('bytes', {})])"

# Missions 3/4: numeric amounts
check "M3: 'amount' is numeric in shopfast-app-*" \
  "shopfast-app-*/_mapping/field/amount" \
  "any(f.get('mapping', {}).get('amount', {}).get('type') in ('float','double','long')
      for idx in r.values() for f in [idx.get('mappings', {}).get('amount', {})])"
check "M4: 'amount' is numeric in shopfast-orders-*" \
  "shopfast-orders-*/_mapping/field/amount" \
  "any(f.get('mapping', {}).get('amount', {}).get('type') in ('float','double','long')
      for idx in r.values() for f in [idx.get('mappings', {}).get('amount', {})])"

# Mission 5: geoip present on web docs, healthz noise dropped
check "M5: web documents carry a geoip object" \
  "shopfast-web-*/_count?q=_exists_:geoip" "r.get('count', 0) > 0"
check "M5: no /healthz documents in shopfast-web-*" \
  "shopfast-web-*/_count?q=request:%22/healthz%22" "r.get('count', 1) == 0"

# Mission 6: clean main indices, populated dead letter
check "M6: no parse-failure tags in business indices" \
  "shopfast-web-*,shopfast-app-*,shopfast-orders-*/_count?q=tags:_grokparsefailure%20OR%20tags:_dissectfailure%20OR%20tags:_csvparsefailure%20OR%20tags:_dateparsefailure" \
  "r.get('count', 1) == 0"
check "M6: shopfast-deadletter exists and is non-empty" \
  "shopfast-deadletter*/_count" "r.get('count', 0) > 0"

echo "======================"
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
