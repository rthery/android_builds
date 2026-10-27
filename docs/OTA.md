# Custom OTA feed

Packages are versioned releases in [android_builds-releases](https://github.com/rthery/android_builds-releases). The small JSON index stays here, as an asset of the rolling `ota-feed` release, so the URL built into installed devices does not depend on the repository holding vendor binaries:

```text
https://github.com/rthery/android_builds/releases/download/ota-feed/{device}-{type}.json
```

The Updater substitutes the device codename and lowercase release type and follows GitHub's redirect to the asset. Each release replaces only its own `{device}-{type}.json` asset; to roll back, upload the previous JSON again. The URL is built into every installed build, so the tag and asset names must never change. A new Android base needs its own tag and product property. The initial asset is `bullhead-unofficial.json`. Its empty response intentionally offers no updates until a signed package and upgrade path have been tested. An empty list is not evidence that OTA installation works.

The bullhead product sets `lineage.updater.uri` for future builds. Existing installed builds are unaffected. The Updater's separate developer-mode official staging option can override this property; leave that option off for this custom feed.

Only publish entries for the correct device, Android base, release type and tested signing lineage. Reject older/equal timestamps and unsupported data migrations. Test candidates privately before adding a stable entry. Other devices and Android bases need separate feeds and product configuration.

The checked-out Updater requires top-level `error`, `id`, `response`; nonempty entries require its JsonValidator fields as well as the parser's `datetime` and `size`. In particular, `id` is SHA-256 and `md5sum` is also required. Generate the feed with `scripts/make-ota-feed.py <signing output dir> --device <codename> --current-feed <published json> --out <dir>`: it checks the OTA metadata against the signed build properties, requires release keys and a newer timestamp than the published feed, and writes the feed, release asset name and checksum file. Upload the package to the matching android_builds-releases tag before replacing the feed asset.

The static feed does not filter by the requesting installed version. Do not list a package until it is compatible with every installed version allowed to use this feed, or introduce version-specific feeds/server filtering first. Channel eligibility, release signing and migration validation remain release gates.
