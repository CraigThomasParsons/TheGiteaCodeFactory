# Example private rules for scripts/sync-moonlighter.sh.
#
# Copy to ~/.config/moonlighter-sync/rules.sh (chmod 600) and replace the
# examples with the details your private upstream contains. Keep the real file
# out of every repository: listing what to remove reveals it.

# sed -E expressions applied, in order, to every copied text file.
rewrite_rules=(
    's#my-org/private-app#owner/ExampleApp#g'
    's#my-username/#owner/#g'
    's#(%h|~)/\.config/my-private-dir/#\1/.config/moonlighter/#g'
)

# Extended regex; any match left after rewriting stops the sync.
# (LAN addresses and /home paths are always checked as well.)
leak_pattern='my-username|my-org|private-app'
