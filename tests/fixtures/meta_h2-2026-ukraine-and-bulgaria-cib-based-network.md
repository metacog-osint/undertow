# Ukraine and Bulgaria-Based Influence Operation Targeting United States, Germany, Italy, the United Kingdom, the Netherlands, France, Belgium, Latvia, Ukraine, and Moldova

Meta disrupted a Ukraine and Bulgaria-based Coordinated Inauthentic Behavior (CIB) network targeting United States, Germany, Italy, the United Kingdom, the Netherlands, France, Belgium, Latvia, Ukraine, and Moldova. This file contains indicators of compromise and a network summary from Meta’s Adversarial Threat Report H2 2026.

## Meta’s Adversarial Threat Report Network Summary

We disrupted a Coordinated Inauthentic Behavior network originating in Ukraine and Bulgaria and targeting audiences in the United States, Germany, Italy, the United Kingdom, the Netherlands, France, Belgium, Latvia, Ukraine, and Moldova. The operation had a cross-platform presence, including accounts on TikTok, X, and Telegram as well as maintaining their own websites. We removed 72 Facebook accounts and 16 Instagram accounts for violating our policy against Coordinated Inauthentic Behavior. About 500 accounts followed one or more of these Instagram accounts. Meta’s investigation revealed links to a Ukrainian expat in Bulgaria.

The network employed sophisticated grassroots impersonation tactics, creating a series of localized news Pages and standalone websites whose names and languages aligned with their target countries. The operation attempted to make these websites appear authentic by investing in distinct branding, utilizing Large Language Models to generate unique articles interspersed with influence content, and employing fictitious bylines backstopped by fake journalist accounts on our platforms. The network utilized a multi-layered distribution strategy incorporating two distinct amplification clusters to distribute narratives from the core Pages. The first was a traditional network of inauthentic amplification accounts that posted URLs directly to target Pages, while the second cluster exhibited scripting signals by posting identical narratives across different accounts in very short succession. We observed that network operators produced and amplified narratives advocating support for Ukraine's military, raising fears of Russian influence in the European Union, and undercutting politicians deemed pro-Russian.

## Indicators of Compromise

*Note: URLs have been defanged for safety. Replace `[.]` with `.` to resolve.*

| Indicator Type | Indicator Value |
| :--- | :--- |
| Domain | `fixture-6d1be9-1[.]invalid` |
| Domain | `fixture-6d1be9-2[.]invalid` |
| Domain | `fixture-6d1be9-3[.]invalid` |
| Domain | `fixture-6d1be9-4[.]invalid` |
| Domain | `fixture-6d1be9-5[.]invalid` |
| Domain | `fixture-6d1be9-6[.]invalid` |
| Domain | `fixture-6d1be9-7[.]invalid` |
| Domain | `fixture-6d1be9-8[.]invalid` |
| Domain | `fixture-6d1be9-9[.]invalid` |
| Social Media Account | `https://x[.]com/fixture_6d1be9_10` |
| Social Media Account | `https://t[.]me/fixture_6d1be9_11` |
| Social Media Account | `https://www[.]tiktok[.]com/@fixture_6d1be9_12` |
| Social Media Account | `https://t[.]me/fixture_6d1be9_13` |
| Social Media Account | `https://t[.]me/fixture_6d1be9_14` |
| Social Media Account | `https://t[.]me/fixture_6d1be9_15` |
| Social Media Account | `https://t[.]me/fixture_6d1be9_16` |
| Social Media Account | `https://www[.]tiktok[.]com/@fixture_6d1be9_17` |
| Social Media Account | `https://www[.]tiktok[.]com/@fixture_6d1be9_18` |
| Social Media Account | `https://www[.]tiktok[.]com/@fixture_6d1be9_19` |
| Social Media Account | `https://x[.]com/fixture_6d1be9_20` |
| Social Media Account | `https://x[.]com/fixture_6d1be9_21` |
| Social Media Account | `https://x[.]com/fixture_6d1be9_22` |
## Cross-Links

- **Full ATR Report:** [Meta Adversarial Threat Report H2 2026](TBD)
- **AlienVault OTX Pulse:** [h2-2026-ukraine-and-bulgaria-cib-based-network on OTX](https://otx.alienvault.com/pulse/h2-2026-ukraine-and-bulgaria-cib-based-network)
- **IOC File (GitHub):** [h2-2026-ukraine-and-bulgaria-cib-based-network on GitHub](https://github.com/facebook/threat-research/blob/main/indicators/h2-2026-ukraine-and-bulgaria-cib-based-network.md)
