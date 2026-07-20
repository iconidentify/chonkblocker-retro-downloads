# Chonk Blocker Retro downloads

This public repository contains release notes and downloadable builds for
[Chonk Blocker Retro](https://chonkblocker.com/retro). The game is free.

Source code, signing credentials, and build infrastructure remain in private
repositories. The signed build pipeline uploads binaries directly to a public
GitHub Release, then a dedicated deploy key pushes a short-lived `incoming/*`
branch containing only its manifest and notes. GitHub Actions downloads and
checksum-validates every public asset, updates the version index, and deletes
the incoming branch. The same validated job mirrors the current 256 KiB ROM at
`browser/Chonk-Blocker-Retro.sfc` for the client-only player on the website.

Use the website for the polished download experience. This repository exists
as the public, auditable release channel.
