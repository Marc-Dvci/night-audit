// The footer: the evidence chain hash, and "Verify this night", which recomputes the chain in the browser and prints
// it like a line printer (ui-kit Req 6.1-6.3).

import type { Source } from "../api";
import { esc } from "../format";
import type { VerifyState } from "../state";
import type { RunResult } from "../types";

export function footer(run: RunResult, src: Source, verify: VerifyState): string {
  const actions = [
    `<button type="button" class="text-button" data-action="verify"${verify.busy ? " disabled" : ""}>Verify this night</button>`,
    verify.ok === true && !verify.tampered
      ? `<button type="button" class="text-button" data-action="tamper">Change one byte</button>`
      : "",
    verify.tampered ? `<button type="button" class="text-button" data-action="restore">Restore the original</button>` : "",
    `<a class="text-button" href="${esc(src.zip(run.run_id))}" download>Download the evidence pack</a>`,
  ].join("");
  const tone = verify.ok === true ? " ok" : verify.ok === false ? " failed" : "";
  return `<footer class="foot" aria-labelledby="foot-title">
    <h2 class="rule-title" id="foot-title">Evidence</h2>
    <dl class="printout">
      <div><dt>Evidence chain</dt><dd class="mono hash" id="chain-hash">${esc(run.evidence_chain_hash ?? "none")}</dd></div>
      <div><dt>Control</dt><dd class="mono hash">${esc(run.control_id)} · ${esc(run.control_hash)}</dd></div>
      <div><dt>Run</dt><dd class="mono">${esc(run.run_id)}</dd></div>
    </dl>
    <p class="foot-intro">The evidence pack is every ledger row and every finding, each row hashed with the one before. Verify it here, in this browser, or offline with <code>nightaudit verify &lt;pack&gt;</code>.</p>
    <div class="actions">${actions}</div>
    <pre class="printer" id="printer" aria-hidden="true">${esc(verify.lines.join("\n"))}</pre>
    <p class="verdict${tone}" id="verdict" role="status">${esc(verify.verdict)}</p>
  </footer>`;
}
