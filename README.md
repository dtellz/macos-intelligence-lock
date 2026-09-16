<h1 align="center">macOS Intelligence Lock</h1>

<p align="center">
  <a href="https://github.com/dtellz/macos-intelligence-lock/actions/workflows/tests.yml">
    <img src="https://github.com/dtellz/macos-intelligence-lock/actions/workflows/tests.yml/badge.svg?branch=master" alt="Tests">
  </a>
</p>

**Prefer on-device AI. Keep the restriction visible, understandable, and reversible.**

`apple-pcc-block.sh` manages a small, labeled section of `/etc/hosts` for three hostnames that Apple documents as Private Cloud Compute (PCC) endpoints. The goal is to reduce access to those cloud-inference paths without removing Apple's local models or modifying protected system components.

> **Important:** This is a best-effort hostname-resolution block, **not an outbound firewall or a complete cloud-AI off switch**. It does not make macOS technically incapable of contacting PCC. Read [Limitations](#limitations) before relying on it.

**Status:** Prototype. The endpoint list was checked against Apple's documentation on **2026-09-16**. End-to-end blocking and compatibility with macOS 27 have not been validated here. The exit-cleanup bug in the initial version is fixed and covered by regression tests. Other [known implementation issues](#known-implementation-issues) remain before a production release.

## Why this project exists

The starting point is a simple preference:

> I want to use a model on my computer without also opting into cloud inference.

Apple Intelligence includes both on-device processing and server-side processing through Private Cloud Compute. Apple says more demanding requests can be handled by PCC rather than entirely on the device. These are different processing locations, even when both are presented as Apple Intelligence. [1]

For a privacy-conscious person, the question is not only **who can read the data**, but also **whether the data needs to leave the device at all**.

**Minimize data movement.** A private draft, unreleased source code, or personal notes may be material someone is comfortable processing locally but not submitting for remote inference. A preference for local processing does not require evidence that a cloud provider is behaving improperly.

**Keep local and cloud choices separate.** Wanting help rewriting a paragraph does not necessarily imply wanting a remote model involved. Some users would rather accept a less capable answer—or an unavailable feature—than expand where their information is processed.

**Make the configuration easy to remember and undo.** A readable script, named entries, explicit commands, and backups are easier to inspect later than an unexplained system tweak. This repository is intended to record what was changed and why, not hide another background service on the Mac.

These are the project's goals, not guarantees that a hosts-file change can fully enforce them.

## What about Apple's privacy protections?

Apple documents technical safeguards for PCC, including encrypted requests to verified compute nodes, controls intended to prevent privileged access to user data, no retention of request data after processing, and software transparency for independent researchers. [2]

This project is not evidence that those protections are ineffective. It addresses a different preference: **protected remote processing is still remote processing**. Someone may recognize the design's protections and nevertheless choose not to use the service.

A hostname block is also not a substitute for a security assessment or an organization's approved controls for confidential information.

## What the script changes

The script adds these entries between its own start and end markers:

```text
# >>> APPLE PRIVATE CLOUD COMPUTE BLOCK >>>
# Managed by apple-pcc-block.sh
# Apple-published Private Cloud Compute endpoints.
0.0.0.0 apple-relay.cloudflare.com
::      apple-relay.cloudflare.com
0.0.0.0 apple-relay.fastly-edge.com
::      apple-relay.fastly-edge.com
0.0.0.0 cp4.cloudflare.com
::      cp4.cloudflare.com
# <<< APPLE PRIVATE CLOUD COMPUTE BLOCK <<<
```

Apple lists all three hostnames for PCC over TCP and UDP port 443. [3] **The script itself does not filter ports or packets**: it substitutes IPv4 and IPv6 addresses when software resolves these exact names through a path that honors `/etc/hosts`.

Before rewriting `/etc/hosts`, the script makes a timestamped backup. It then writes the edited contents, sets the file's permissions to `644`, and attempts to flush the system's name-resolution caches. `disable` removes the marked section rather than restoring the entire backup.

There is no installed daemon, scheduled task, project telemetry, automatic blocklist download, or model modification. The `status` command queries the macOS resolver; those queries can generate DNS traffic when local overrides are absent or ineffective.

The implementation is contained in [`apple-pcc-block.sh`](apple-pcc-block.sh).

## Review and use

Run these commands from the directory containing the script. Review the [known implementation issues](#known-implementation-issues) before enabling it, and do not apply it to a managed work Mac without the administrator's approval.

```bash
# Read the script before giving it administrator privileges.
less apple-pcc-block.sh

chmod +x apple-pcc-block.sh

# Print the proposed hosts-file block without installing it.
./apple-pcc-block.sh show

# Install the block; the script requests sudo privileges.
./apple-pcc-block.sh enable

# Inspect the markers and the resolver's current output.
./apple-pcc-block.sh status
```

| Command | Purpose |
| --- | --- |
| `show` | Print the proposed managed section without changing the hosts file. |
| `enable` | Add or replace that section, with a backup before rewriting. |
| `status` | Report marker presence and display system-resolver results. |
| `disable` | Remove the managed section, with a backup before rewriting. |

The script uses macOS command-line utilities; it does not require Homebrew. The local model must already be available on the Mac. This script does not enable Apple Intelligence, download a model, or override Apple's hardware, language, or availability requirements.

The entries remain until `/etc/hosts` is changed again. There is no background enforcement: another administrator, management tool, or hosts-file editor can replace them. **Deleting the script or repository does not remove the installed entries.**

## Keep inference explicitly on-device

In Shortcuts, select **On-Device** in the **Use Model** action. Apple documents this option as not requiring a network connection; its Cloud and Cloud Pro options use PCC. [4]

A minimal workflow is:

```text
Ask for Input → Use Model: On-Device → Show Content
```

Review the entire shortcut, not just its model selection. Another action could upload the input or result independently. Likewise, choosing a local model does not by itself prevent the surrounding application from syncing or transmitting information.

## Could this affect other Apple services?

**Yes—features that need PCC may stop working, time out, or retry.** A feature might offer another processing path, but this project does not guarantee an automatic local fallback. Do not interpret an answer appearing as proof that processing stayed on-device.

The blocklist deliberately excludes these separately documented services: [3]

| Not blocked by this script | Apple's listed purpose |
| --- | --- |
| `apple-relay.apple.com` | Apple Intelligence Extensions |
| `guzzoni.apple.com` | Siri and dictation |
| `*.smoot.apple.com` | Search services, including Spotlight and Lookup |

It does not add broad Apple, Cloudflare, or Fastly domain blocks, or block shared CDN IP ranges. That narrow scope is intended to limit collateral effects, **not to promise that every unrelated Apple feature will remain unaffected**.

In particular, this is not a way to disable all Siri traffic, AI extensions, third-party AI applications, iCloud synchronization, or other network services. Leaving them outside the blocklist is a scope decision, not a privacy guarantee about them.

When troubleshooting a new problem, temporarily run `disable`, restart the affected application, and compare its behavior using non-sensitive input. An operating-system update can also change dependencies, so recheck after updates.

## Verify the configuration

### Inspect local resolution

```bash
./apple-pcc-block.sh status
```

Check that each listed hostname returns the configured `0.0.0.0` and/or `::` entries rather than a public address. One hostname can also be inspected directly:

```bash
dscacheutil -q host -a name apple-relay.cloudflare.com
```

**`INSTALLED` only means the script found its two marker lines.** It is not a validation of every entry, a firewall test, or proof that no request left the computer. The script's `status` output is diagnostic, not a machine-verifiable security result.

### Test behavior with harmless data

Once the model is downloaded and available, test an explicitly on-device shortcut with network connectivity disabled. This checks that the particular workflow can work offline—not that all other workflows are local. [4]

A separate cloud-path test can use a fresh shortcut containing only a fixed prompt, a cloud-model action, and a display action. Use a prompt such as `Reply with the word test`, with no clipboard, files, or other personal context attached. **A failed block could allow this test prompt to reach the cloud.** A network error is consistent with blocking, but a single failure does not prove complete coverage.

### Review Apple's activity report

Apple documents an **Apple Intelligence Report** under **System Settings → Privacy & Security**. Select a reporting duration and export activity to inspect recorded PCC requests. A duration change can leave the report empty until new requests occur. [1]

Treat the report as supplementary evidence, not an independent network-enforcement mechanism. An empty report is not proof that all AI-related traffic is blocked. Review and redact exported reports before sharing them.

## Limitations

**Name resolution is not network enforcement.** Software may use cached addresses, existing connections, another resolver, a remotely resolving proxy, or a direct IP address. A hosts-file edit does not terminate connections already established. These are limitations of the mechanism, not claims that Apple has been observed deliberately bypassing this script.

**The list is finite and can become stale.** New or alternate hostnames are not covered. The entries are exact-name overrides, not wildcard rules. There is no automatic discovery or updating.

**Other cloud paths remain outside scope.** An application or extension can send data to a service not listed here. Blocking PCC does not establish a system-wide local-only AI policy.

**Stronger requirements need stronger controls.** A requirement that inference data must never leave the device needs independently enforced network restrictions or network isolation, with any permitted destinations, proxies, and tunnels accounted for. This script alone is not sufficient for that requirement.

## Undo the change

```bash
./apple-pcc-block.sh disable
./apple-pcc-block.sh status
```

Backups are stored alongside the hosts file, with names such as:

```text
/etc/hosts.before-pcc-block.20260916-083000
```

Use `disable` rather than blindly copying an old backup over `/etc/hosts`: a full restore could overwrite unrelated changes made since the backup.

For manual recovery, carefully remove only the managed section—including its two markers—from `/etc/hosts`, preserve the other entries, and refresh the caches:

```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

Do not delete or replace the entire hosts file. Keep backup files out of a public repository; they may contain private network names.

## Known implementation issues

The current script is a prototype, not a hardened privileged configuration manager:

- **Marker validation is missing:** the removal routine assumes a well-formed, uniquely paired block. A missing or misplaced end marker can cause unrelated lines to be removed. Keep the markers intact; production use should validate them before editing.
- **Writes are not atomic or locked:** interruptions or concurrent hosts-file edits can cause problems. Backup names also have only second-level timestamp precision. Avoid concurrent runs; stronger safeguards are needed for unattended deployment.

The regression tests below exercise shell behavior in a sandbox. They do not eliminate these remaining write-safety limitations.

## Regression tests

Run the included tests from the repository directory with Python 3.8 or later and Bash available:

```bash
python3 test_apple_pcc_block.py
```

The tests instrument a **temporary copy** of the script to use a temporary hosts file, bypass privilege escalation, and replace the macOS resolver/cache commands with a no-op. They do not edit the real `/etc/hosts`, invoke `sudo`, or change system DNS caches. Instrumentation fails rather than running the copy if expected replacement points are missing.

Ten checks cover shell syntax, `show`, `status`, enable/disable cleanup, preserving entries surrounding a managed block, repeated enable, an enable/disable round trip, no-op disable, cleanup after a simulated backup failure, and command exit statuses. Temporary paths include spaces, quotes, and shell metacharacters to exercise safe quoting.

The original `tmp: unbound variable` failure was reproduced before the fix. The corrected script captures and shell-quotes the temporary pathname when registering each `EXIT` trap, rather than looking up the function-local variable after the function has returned. Both `enable` and `disable` are fixed; error detection remains enabled.

All ten tests passed with **Bash 5.2 on Linux**. This is not an end-to-end test of PCC blocking, model availability, the macOS bundled Bash, or macOS 27 compatibility.

## Maintenance and contributions

Recheck Apple's endpoint documentation and repeat local tests after relevant macOS updates. Record the OS version, build, endpoint-review date, and observed results when reporting compatibility. Do not describe an untested configuration as guaranteed protection.

Changes to the blocklist should include an authoritative source and an explanation of possible effects on other services. Reports about bypasses, unexpected breakage, and rollback behavior are useful; redact prompts, network identifiers, and other private information before publishing them.

## Sources

Apple documentation consulted on **2026-09-16**. Endpoint documentation is evidence of intended network use, not certification that this script blocks every possible path.

1. [Apple Support — Apple Intelligence and privacy on Mac](https://support.apple.com/guide/mac-help/mchlfc0d4779/mac)
2. [Apple Security Research — Private Cloud Compute: A new frontier for AI privacy in the cloud](https://security.apple.com/blog/private-cloud-compute/)
3. [Apple Support — Use Apple products on enterprise networks](https://support.apple.com/101555)
4. [Apple Support — Use Apple Intelligence in Shortcuts on Mac](https://support.apple.com/guide/shortcuts-mac/mchl91750563/mac)

---

Independent project. Not affiliated with or endorsed by Apple. No guarantee of complete cloud isolation or compatibility with every macOS release.
