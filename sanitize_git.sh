#!/bin/bash
set -e

SECRET="4Kib2uPPgTmBmlXoYi9tDmgJH-t-1nZBIXgBMPf7ljQ"
REDACTED="[REDACTED_API_KEY]"

echo "Sanitizing git history from $SECRET..."

export FILTER_BRANCH_SQUELCH_WARNING=1

git filter-branch --force --tree-filter "\
find . -type f -not -path '*/.git/*' -exec grep -Il '\$SECRET' {} + | \
xargs -I {} sed -i '' 's/\$SECRET/\$REDACTED/g' {} || true" \
--msg-filter "sed 's/\$SECRET/\$REDACTED/g'" HEAD~8..HEAD

echo "Git history sanitized successfully."
