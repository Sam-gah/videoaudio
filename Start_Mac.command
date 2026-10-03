#!/bin/zsh
cd "${0:A:h}"
if command -v python3 >/dev/null 2>&1; then
  python3 app.py
elif [[ -x /opt/anaconda3/bin/python3 ]]; then
  /opt/anaconda3/bin/python3 app.py
else
  echo "Python 3.10 or later is required. See README.md."
  read "?Press Return to close."
fi
