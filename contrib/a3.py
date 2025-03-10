from babel import Locale

from rigour.territories import get_territory

locale = Locale("en", "US")
for t in locale.territories:
    territory = get_territory(t.lower())
    if territory is None:
        continue
    tx = locale.territories[t]
    print(
        territory.code,
    )
