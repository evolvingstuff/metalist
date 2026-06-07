# TODO

## Default Namespace Identity And Recovery

- Current protection is name-based: namespace `default` cannot be deleted, but a namespace that originated as `default` and was restored/imported/renamed as another name is treated as ordinary.
- First-run startup can bootstrap literal `default` by prompting for launch ports and saving its launch profile, which creates `namespaces/default/default.metalist.db`.
- Later flows do not currently recreate `default` if it disappears, and deleting the last usable non-default namespace can leave no practical fallback.

Future fix:
- Define the intended invariant explicitly: either literal `default` must always exist, or at least one usable namespace must remain.
- Before deleting any namespace, verify the post-delete namespace set will still include a usable fallback with a database and launch profile.
- If literal `default` is missing and should be required, offer an explicit repair/bootstrap flow instead of silently recreating it.
- If identity matters beyond the literal name, add stable namespace metadata so a restored/imported namespace can be recognized without relying only on its directory name.
