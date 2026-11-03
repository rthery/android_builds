# Custom OTA feed

Packages are versioned releases of this repository. The small JSON index is an asset of the rolling `ota-feed` release:

```text
https://github.com/rthery/android_builds/releases/download/ota-feed/<rom><base>-{device}.json
```

Each ROM and Android base has its own feed file, so one never offers a package to another: LineageOS 22 reads `lineage22-{device}.json`, and a future /e/OS base gets its own prefix, for example `eos-a15-{device}.json`. The whole URL is a system property value, so it must fit in 91 bytes; every build is UNOFFICIAL, so the name carries no `{type}`. The device tree sets the URL in `lineage.updater.uri` and the tree's `build.conf` names the same file in `BUILD_FEED_ASSET`. The Updater substitutes the device codename and follows GitHub's redirect to the asset. Each release replaces only its own feed asset; to roll back, upload the previous JSON again. The URL is built into every installed build, so the tag and asset names must never change. A tree's first release creates its feed file. An empty or missing feed offers no updates, which is not evidence that OTA installation works.

Existing installed builds keep the URL they were built with. The Updater's separate developer-mode official staging option can override this property; leave that option off for this custom feed.

Only publish entries for the correct device, Android base, release type and tested signing lineage. Reject older/equal timestamps and unsupported data migrations. Test candidates privately before adding a stable entry. Other devices and Android bases need separate feeds and product configuration.

The checked-out Updater requires top-level `error`, `id`, `response`; nonempty entries require its JsonValidator fields as well as the parser's `datetime` and `size`. In particular, `id` is SHA-256 and `md5sum` is also required. Generate the feed with `scripts/make-ota-feed.py <signing output dir> --device <codename> --feed-name <feed file> --current-feed <published json> --out <dir>` (LineageOS packages: `--filename-prefix lineage-`): it checks the OTA metadata against the signed build properties, requires release keys and a newer timestamp than the published feed, and writes the feed, release asset name and checksum file. Upload the package to its release tag before replacing the feed asset. LineageOS 22.2 releases go through the workflow's `release` mode, whose `release` job replaces the feed ([build automation](BUILD_AUTOMATION.md)).

The static feed does not filter by the requesting installed version. Do not list a package until it is compatible with every installed version allowed to use this feed, or introduce version-specific feeds/server filtering first. Channel eligibility, release signing and migration validation remain release gates.
