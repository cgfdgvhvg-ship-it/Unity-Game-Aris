# Offline gameplay sound effects

Unity packages 43 mono AudioClips under Assets/Resources/SFX. No clips are downloaded during play.

- 28 deterministic original WAVs use 22,050 Hz, 16-bit mono PCM. Tools/Audio/generate_sfx.py generates the clips and their AudioImporter metadata. Run it with --check to verify their bytes. The Gloo Wall deployment clip was created for this integration.
- 15 recorded Kenney Impact Sounds OGG clips provide grass and concrete footsteps, punch impacts and landing or metal impacts. The [publisher lists CC0](https://kenney.nl/assets/impact-sounds). The binaries were carried over unchanged from review/offline-mobile-audio-20261109. Their original blob hashes were checked in [run 42548737813](https://github.com/sundamunda289-art/Unity-Game-Aris/actions/runs/42548737813) against the [pinned sample mirror](https://github.com/GeorgeQLe/assets-sfx-combat/tree/9662dc1bed3b06ae753045915f9accfac044c7ce/assets/kenney/impact-sounds/Audio).

The saved player creates one audio director and uses the existing camera's AudioListener. Shots play when ammunition is consumed. Steps use grounded travel distance, jump and touchdown use movement events, and Gloo Wall audio plays only after placement. Drop and vehicle state drive three local loops for the aircraft, wind and car engine. Twelve reusable spatial sources handle short effects. Weapon, aircraft, canopy, vehicle and Gloo cues use original synthesized clips.

Unity's batch gameplay verifier checks clip imports, the saved camera listener and gameplay cue routing. Android speaker volume and sound quality require a phone playback test.
