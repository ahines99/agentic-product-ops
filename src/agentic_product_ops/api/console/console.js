"use strict";
const $ = id => document.getElementById(id);
let current = null, plan = null, settings = null, requestKey = null, requestBody = null;
let approvalKey = null, laneKey = null, timer = null;
async function api(path, method = "GET", body, key) {
  const headers = {"X-Product-Ops-UI": "1"};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (key) headers["Idempotency-Key"] = key;
  const response = await fetch(path, {method, headers, credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body)});
  if (!response.ok) {
    if (response.status === 401) throw new Error("Your operator session is closed. Reopen Product Ops with the local launch shortcut.");
    if (response.status === 409) throw new Error("This request changed. Refresh and review the latest proposal before retrying.");
    if (response.status === 403) throw new Error("A policy or approval gate is holding this action. Refresh to check the proposal and blockers.");
    throw new Error(`Request held (${response.status}). Your prompt has not been approved or published by this action.`);
  }
  return response.json();
}
function notice(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}
function appendText(parent, tag, text) {
  const element = document.createElement(tag); element.textContent = text; parent.append(element); return element;
}
async function connect() {
  const code = new URLSearchParams(location.hash.slice(1)).get("launch");
  history.replaceState(null, "", location.pathname);
  try {
    if (code) await api("/v1/local/session", "POST", {code});
    settings = await api("/v1/local/status");
    $("connection").textContent = settings.analysis_enabled
      ? "Connected. Your request will be analyzed before you review and approve proposed tickets."
      : "Connected. Requests can be saved; analysis is paused until a new model budget is authorized.";
    $("submit").textContent = settings.analysis_enabled ? "Prepare proposed tickets" : "Save request for analysis";
    $("submit").disabled = false; $("logout").hidden = false;
    const saved = sessionStorage.getItem("apo-request");
    if (saved && /^[0-9a-f-]{36}$/.test(saved)) {
      current = {specification_id: saved}; $("result").hidden = false;
      $("request-id").textContent = "Request " + saved; await refresh();
    }
  } catch (error) {
    $("connection").textContent = error.message + " Use .local/pilot/prompt/Open Product Ops.cmd to connect securely.";
    $("connection").classList.add("error");
  }
}
$("intake").addEventListener("submit", async event => {
  event.preventDefault(); $("submit").disabled = true; $("result").hidden = false;
  const body = {repository: $("repository").value.trim(), source: $("prompt").value.trim()};
  const serialized = JSON.stringify(body);
  if (serialized !== requestBody) { requestKey = crypto.randomUUID(); requestBody = serialized; }
  notice("Saving your request…");
  try {
    const receipt = await api("/v1/intakes/prompts", "POST", body, requestKey);
    current = {specification_id: receipt.specification_id};
    sessionStorage.setItem("apo-request", receipt.specification_id);
    $("request-id").textContent = "Request " + receipt.specification_id;
    await refresh();
  } catch (error) { notice(error.message, true); }
  finally { $("submit").disabled = false; }
});
async function refresh() {
  if (!current) return;
  clearTimeout(timer); timer = null;
  $("approve").disabled = true; plan = null; approvalKey = null; $("exact-plan").hidden = true;
  $("lane").hidden = true; $("approve").hidden = false;
  try {
    const base = "/v1/specifications/" + encodeURIComponent(current.specification_id);
    const [spec, tickets, review] = await Promise.all([api(base), api(base + "/tickets"), api(base + "/review")]);
    current = spec;
    $("tickets").replaceChildren(); $("questions").replaceChildren(); $("blockers").replaceChildren();
    const findings = [...tickets.ticket_findings, ...tickets.delivery_findings, ...(review.blocking_findings || [])];
    const reviewed = review.result && review.result.review;
    for (const finding of (reviewed ? reviewed.findings : [])) if (finding.blocking) findings.push(finding.summary || finding.kind || "Review raised a blocker.");
    for (const finding of new Set(findings)) appendText($("blockers"), "li", finding);
    const open = spec.unresolved_questions.filter(q => !q.resolution);
    const optional = open.filter(q => !q.blocking);
    let optionalList = null;
    if (optional.length) {
      // Optional questions never block approval; answering one starts a new revision.
      optionalList = document.createElement("details"); optionalList.className = "optional";
      appendText(optionalList, "summary", "Optional notes (" + optional.length + ") · not needed to approve");
      appendText(optionalList, "p", "The implementer will choose a sensible default for each of these. " +
        "Answer one only if the default matters to you: that creates a new revision that needs fresh analysis and approval.");
    }
    if (open.some(q => q.blocking)) appendText($("questions"), "h3", "Answer required before approval");
    for (const question of [...open.filter(q => q.blocking), ...optional]) {
      const row = document.createElement("div"); row.className = "question";
      appendText(row, question.blocking ? "h3" : "h4", question.question); appendText(row, "p", question.why_it_matters);
      const answer = document.createElement("textarea"); answer.rows = 2; answer.maxLength = 16000;
      answer.setAttribute("aria-label", "Answer: " + question.question); row.append(answer);
      const button = appendText(row, "button", question.blocking ? "Submit answer" : "Answer anyway");
      if (!question.blocking) button.className = "quiet";
      let answerKey = null, answerText = null;
      button.addEventListener("click", async () => {
        if (!answer.value.trim()) return; button.disabled = true;
        if (answerText !== answer.value.trim()) { answerText = answer.value.trim(); answerKey = crypto.randomUUID(); }
        try { await api(base + "/clarifications", "POST", {revision: spec.revision, content_digest: spec.content_digest,
          question_id: question.id, answer: answerText}, answerKey); await refresh(); }
        catch (error) { notice(error.message, true); button.disabled = false; }
      });
      (question.blocking ? $("questions") : optionalList).append(row);
    }
    if (optionalList) $("questions").append(optionalList);
    for (const ticket of tickets.tickets) {
      const article = document.createElement("article"); appendText(article, "h3", ticket.id + " · " + ticket.title);
      const details = document.createElement("details"); appendText(details, "summary", "Read proposed ticket");
      appendText(details, "pre", ticket.description); article.append(details); $("tickets").append(article);
    }
    notice(!settings.analysis_enabled && !reviewed ? "Saved. Paid analysis is disabled; no tickets have been published."
      : reviewed ? "Proposal available. Review the tickets below and approve the exact plan when ready."
      : "Analysis or clarification is pending. Refresh to check progress.");
    $("approval-note").textContent = "Approval requires a completed review and an exact publication plan. " +
      (settings.publication_enabled ? "Delivery eligibility is checked separately." : "Linear publication is currently disabled.");
    const ready = reviewed && !reviewed.findings.some(f => f.blocking) && tickets.ticket_findings.length === 0;
    const lane = settings.publication_enabled ? await api(base + "/documentation-lane").catch(() => null) : null;
    if (ready && lane && lane.eligible) {
      // A single inert documentation addition: Delivery OS can make it once the lane is chosen.
      $("lane").hidden = false; $("approve").hidden = true; $("lane-use").disabled = false;
      $("lane-note").textContent = "This request adds " + lane.path + " with the content below. " +
        "Choosing the documentation lane is your security decision: Product Ops runs one paid review, " +
        "then you approve the exact tickets and publish. Delivery OS then adds the file on a review branch for you to merge.";
      $("lane-content").textContent = lane.content;
    } else if (ready) {
      try {
        plan = (await api(base + "/plan")).plan;
        $("plan").textContent = JSON.stringify(plan, null, 2); $("exact-plan").hidden = false;
        $("approve").disabled = false;
        if (lane && lane.promoted) $("approval-note").textContent =
          "Documentation lane chosen. Approve and publish these exact tickets; Delivery OS picks them up from Linear.";
      } catch (_) { $("approval-note").textContent = "The proposal is held by a current policy, scope, or ambiguity gate."; }
    }
    const watching = await showPublication(base);
    // Keep the page current while analysis runs or Delivery OS works; never while you answer.
    if ((settings.analysis_enabled && !reviewed && !open.length) || watching) timer = setTimeout(refresh, 15000);
  } catch (error) { notice(error.message, true); }
}
const DELIVERY = {
  NOT_STARTED: "Waiting for Delivery OS to pick up the tickets.",
  IN_DELIVERY: "Delivery OS is working on it.",
  IN_REVIEW: "Delivery OS finished: a review branch is ready in the repository. Merging it is yours.",
  DELIVERED: "Delivered.",
  DELIVERY_BLOCKED: "Delivery OS stopped. See the ticket in Linear for the reason.",
  CANCELED: "The tickets were cancelled in Linear.",
};
async function showPublication(base) {
  $("publication").hidden = true; $("publish").hidden = true; $("reconcile").hidden = true;
  $("delivery-note").textContent = "";
  if (!settings.publication_enabled) return false;
  let state, delivery;
  try { ({state, delivery} = await api(base + "/state")); } catch (_) { return false; }
  const notes = {
    APPROVED: "Approved. Publishing creates exactly the tickets in the approved plan.",
    EXPIRED: "The approval expired before publication. Approve the same plan again to publish.",
    LINEAR_PUBLISHING: "Publication started but has not finished. Publish again to continue.",
    RECONCILIATION_REQUIRED: "Linear did not confirm a ticket. Check Linear before anything else is sent; nothing is created twice.",
    PUBLISHED: "Published to Linear.",
    HANDOFF_READY: "Published to Linear and handed off.",
  };
  if (!notes[state]) return false;
  $("publication").hidden = false; $("publication-note").textContent = notes[state];
  $("publish").hidden = !["APPROVED", "LINEAR_PUBLISHING"].includes(state);
  $("reconcile").hidden = state !== "RECONCILIATION_REQUIRED";
  const overall = delivery && delivery.overall;
  if (overall && DELIVERY[overall]) $("delivery-note").textContent = "Delivery: " + DELIVERY[overall];
  return ["PUBLISHED", "HANDOFF_READY"].includes(state) && !["DELIVERED", "DELIVERY_BLOCKED", "CANCELED"].includes(overall);
}
async function publication(action) {
  if (!current) return;
  if (action === "publish" && !window.confirm("Create the approved tickets in Linear now?")) return;
  $("publish").disabled = true; $("reconcile").disabled = true;
  try {
    const result = await api("/v1/specifications/" + current.specification_id + "/" + action, "POST", {},
      action === "publish" ? crypto.randomUUID() : undefined);
    notice(result.complete ? "All approved tickets are in Linear."
      : "Linear did not confirm every ticket. Use Check Linear; nothing will be created twice.", !result.complete);
  } catch (error) { notice(error.message, true); }
  finally { $("publish").disabled = false; $("reconcile").disabled = false; await refresh(); }
}
$("publish").addEventListener("click", () => publication("publish"));
$("reconcile").addEventListener("click", () => publication("reconcile"));
$("refresh").addEventListener("click", refresh);
$("approve").addEventListener("click", async () => {
  if (!plan || !current) return; $("approve").disabled = true;
  approvalKey = approvalKey || crypto.randomUUID();
  try {
    await api("/v1/specifications/" + current.specification_id + "/approve", "POST",
      {revision: current.revision, content_digest: current.content_digest, plan_digest: plan.content_digest,
        expires_in_seconds: 1800}, approvalKey);
    notice("Your approval was recorded for this exact revision and plan. Publish below to create the tickets.");
    await refresh();
  } catch (error) { notice(error.message, true); $("approve").disabled = false; }
});
$("lane-use").addEventListener("click", async () => {
  if (!current) return; $("lane-use").disabled = true;
  laneKey = laneKey || crypto.randomUUID();
  notice("Reviewing the documentation change. This takes about a minute…");
  try {
    await api("/v1/specifications/" + current.specification_id + "/documentation-lane", "POST",
      {revision: current.revision, content_digest: current.content_digest}, laneKey);
    laneKey = null;
    notice("Documentation lane chosen. Review the exact tickets, then approve and publish.");
    await refresh();
  } catch (error) { notice(error.message, true); $("lane-use").disabled = false; }
});
$("logout").addEventListener("click", async () => {
  try { await api("/v1/local/logout", "POST", {}); sessionStorage.removeItem("apo-request"); location.reload(); }
  catch (error) { $("connection").textContent = error.message; }
});
connect();
