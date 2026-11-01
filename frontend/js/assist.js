/* assist.js - ASSIST views and workflow wiring: remittance parser,
   copilot, Policy Studio, approvals drawer, run diff, dispute desk,
   command palette, and the boot sequence (last lines of this file). */
/* ---------- Parser / copilot / policy ---------- */
let PARSE_SEQ=0, LAST_PARSED_TEXT=null;
async function runParse(text){
  const seq=++PARSE_SEQ;
  const out=await api("/api/v1/parse",{method:"POST",body:JSON.stringify({text})});
  if(seq!==PARSE_SEQ) return; // a newer edit already superseded this result
  LAST_PARSED_TEXT=text;
    const f=out.fields||{};
    const refs=[...(f.invoice_refs||[]),...(f.po_refs||[])].map(r=>pill(r,"info")).join(" ")||"<small>none</small>";
    const issues=(out.verification?.issues||[]).map(x=>pill(x,"bad")).join(" ");
    const pipeHtml=(out.pipeline&&out.pipeline.length)?`<div class="pipe">${out.pipeline.map(p=>`<div class="step"><div class="st">${esc(p.stage)} <span data-info="${p.stage.startsWith("1")?"pex":p.stage.startsWith("2")?"psch":p.stage.startsWith("3")?"pver":"ptrust"}"></span></div><div class="en">${esc(p.engine)}${p.ms?` - ${p.ms} ms`:""}</div><p>${esc(p.detail)}${p.issues&&p.issues.length?`<br><span style="color:var(--bad)">${p.issues.map(esc).join("; ")}</span>`:""}</p></div>`).join("")}</div>`:"";
    $("parse-out").innerHTML=pipeHtml+`<div class="panel"><h3>Structured result <span data-info="parsefld"></span></h3>
    <div class="detail">Parser: <b>${esc(out.source||"deterministic")}</b> ${out.degraded?pill("deterministic fallback - no Gemini key configured","warn"):""}<br>
    Amount: <b>${f.amount_cents!=null?money(f.amount_cents):"-"}</b> - Payer: <b>${esc(f.payer||"-")}</b> - Claimed deduction: <b>${f.deduction_cents!=null?money(f.deduction_cents):"-"}</b>${f.deduction_reason?` (${esc(f.deduction_reason)})`:""}<br>
    References extracted: ${refs}<br>${out.verification?(out.verification.verified?pill("Verifier: every reference exists in the open ledger","ok"):("Verifier flags: "+issues)):""}</div>
    <details><summary><small>Raw response</small></summary><pre style="background:#0f172a;color:#dbeafe;padding:14px;border-radius:10px;overflow:auto;font-size:12px">${esc(JSON.stringify(out,null,2))}</pre></details></div>`;
    LAST_PARSE=out; renderWireCard();
}
async function doParse(btn){
  if(btn)btn.disabled=true;
  try{ await runParse($("parse-in").value) }
  catch(e){ toast(e.message) } finally{ if(btn)btn.disabled=false }
}
/* Live analysis: the moment text is pasted or typed, the Capture Agent
   reads it and fills the wire card - no button press. A short pause after
   the last keystroke triggers the call, stale results are dropped by
   sequence number, and clearing the box clears the extracted fields. */
function wireAutoParse(){
  const ta=$("parse-in"); if(!ta) return;
  const text=ta.value;
  if(!text.trim() || !/\d/.test(text)){
    PARSE_SEQ++; LAST_PARSE=null; LAST_PARSED_TEXT=null;
    $("wire-amt").textContent="not parsed yet";
    $("wire-meta").textContent="Paste a remittance and it is analyzed automatically - the extracted wire appears here.";
    $("wire-ded").innerHTML=""; $("parse-out").innerHTML="";
    $("stage-btn").disabled=true; $("stage-run-btn").disabled=true; return;
  }
  if(text===LAST_PARSED_TEXT) return;
  $("wire-meta").innerHTML="<small>Analyzing the text...</small>";
  runParse(text).catch(()=>{ if($("wire-meta")) $("wire-meta").innerHTML="<small>Analysis failed - edit the text and it retries automatically.</small>"; });
}
(function(){
  const ta=$("parse-in"); if(!ta) return;
  let t=null;
  ta.addEventListener("input",()=>{ clearTimeout(t); t=setTimeout(wireAutoParse,550); });
  ta.addEventListener("paste",()=>{ setTimeout(wireAutoParse,60); });
})();
function addChat(who,text,cites){
  const log=$("chat"); if(!log) return;
  log.innerHTML+=`<div class="msg ${who==="Copilot"?"bot":""}"><b>${who}:</b> ${esc(text)}${cites&&cites.length?`<div class="cite">${cites.map(c=>pill(c,"info")).join(" ")}</div>`:""}</div>`;
  log.scrollTop=log.scrollHeight;
}
async function askQ(q){$("chat-in").value=q;ask()}
async function ask(){
  const q=$("chat-in").value.trim(); if(!q)return;
  addChat("You",q); $("chat-in").value="";
  try{const a=await api("/api/v1/copilot",{method:"POST",body:JSON.stringify({question:q})}); addChat("Copilot",a.answer,a.citations)}
  catch(e){addChat("Copilot","I could not answer that: "+e.message)}
}
/* ---------- Floating assistant: one chatbot on every page, bottom right.
   Its suggested questions are built from the CURRENT workspace data -
   the actual held payment, the actual unmatched payment, the actual
   disputes - never a fixed list. ---------- */
function toggleChat(){
  const p=$("chatpanel"); if(!p) return;
  p.hidden=!p.hidden;
  if(!p.hidden){ renderSuggestions(); const i=$("chat-in"); if(i) i.focus(); }
}
async function renderSuggestions(){
  const box=$("sugg-box"); if(!box) return;
  const qs=[];
  try{
    const ws=await refreshWorkspace();
    const runs=await api("/api/v1/runs");
    if(runs.length){
      const rid=runs[0].run_id;
      const [ms,xs]=await Promise.all([api(`/api/v1/runs/${rid}/matches`),api(`/api/v1/runs/${rid}/exceptions`)]);
      const nm=xs.find(e=>e.kind==="NO_MATCH");
      if(nm) qs.push(`Why was ${nm.payment_id} not matched?`);
      const held=ms.find(m=>m.status!=="AUTO_POSTED"&&(m.result||{}).status!=="NO_MATCH");
      if(held) qs.push(`Why was ${held.payment_id} held for approval?`);
      if(ms.some(m=>((m.result||{}).deduction||{}).autonomous_action==="AUTO_GENERATE_DISPUTE_CLAIM"))
        qs.push("How much recovery is expected from the disputes?");
      if(xs.length) qs.push("Show exceptions");
      qs.push("What is the touchless rate?");
    } else {
      if(ws&&ws.case) qs.push("What is in this workspace?");
      const inv=await api("/api/v1/invoices");
      if(inv.some(i=>i.due_in_days<0)) qs.push("Which invoices are overdue?");
    }
    qs.push("Which solver is more accurate?");
  }catch(e){ qs.push("What is in this workspace?","Which solver is more accurate?"); }
  box.innerHTML=qs.slice(0,5).map(q=>`<button onclick="askQ('${q.replace(/'/g,"")}')">${esc(q)}</button>`).join("");
}
const POLICY_FIELDS=[
 ["name","Policy name","A label for this behaviour profile. Tenants can run several (for example a stricter month-end profile).","text"],
 ["automation_threshold","Automation threshold (0-1)","Minimum solver confidence for a match to auto-post without a human. Higher is safer and slower; 0.90 is the conservative default.","number"],
 ["age_weight","Age weight (FIFO pressure)","How strongly the solver prefers settling older invoices first. Protects DSO and audit narratives.","number"],
 ["discount_penalty","Discount penalty","Cost assigned to assuming an early-pay discount. Stops the solver inventing discounts to force a fit.","number"],
 ["residual_penalty","Residual penalty","Penalty per unexplained cent. Set astronomically high (1,000,000) so the optimiser would rather propose nothing than hide a residual.","number"],
 ["deduction_penalty","Deduction penalty","Cost of accepting a claimed deduction inside a match. Works with the tolerance and dispute rules below.","number"],
 ["tolerance_writeoff_cents","Tolerance write-off (cents)","Variances at or below this amount (default $25) are written off automatically - disputing them costs more than they are worth.","number"],
 ["auto_dispute_min_recovery_usd","Auto-dispute min recovery ($)","A dispute claim is generated automatically only when expected recovery (win probability x claim - $45 processing cost) exceeds this.","number"],
 ["dispute_processing_cost_usd","Dispute processing cost ($)","The fully-loaded cost of working one dispute. Feeds the expected-value rule honestly instead of disputing everything.","number"],
 ["maker_checker_threshold_cents","Maker-checker threshold (cents)","Matches above this value ($100,000 default) require a second human approver even at full solver confidence.","number"]];
async function loadPolicy(){
  try{const d=await api("/api/v1/policy"); const p=d.policy||d;
    $("policy-src").textContent="Source: "+(d.source||"tenant");
    const POLF={automation_threshold:"auto-post iff OPTIMAL_EXACT_MATCH and confidence >= threshold",age_weight:"objective term per invoice: -(1 + age_days x age_weight)",discount_penalty:"objective cost of setting d_i = 1 (taking a discount)",residual_penalty:"objective cost per residual cent - dominates all other terms",deduction_penalty:"objective cost of setting y = 1 (accepting the claim)",tolerance_writeoff_cents:"claimed <= tolerance -> WRITE_OFF_TOLERANCE",auto_dispute_min_recovery_usd:"dispute iff win_prob x claimed - processing_cost > threshold",dispute_processing_cost_usd:"subtracted in the expected-recovery computation",maker_checker_threshold_cents:"match value above this requires a second approver",name:"profile label only - no mathematical role"};
    $("policy-form").innerHTML=POLICY_FIELDS.map(([k,label,why,type])=>`<div class="polrow"><label for="pol-${k}">${label} ${spec(label,why,POLF[k]||"","Changing this value changes the next run's behaviour; the run records the policy it used.")}</label><input id="pol-${k}" type="${type}" step="any" value="${esc(p[k]??"")}"><div class="why">${why}</div></div>`).join("");
  }catch(e){toast(e.message)}
}
function policyFormBody(){ const body={}; for(const [k] of POLICY_FIELDS){const el=$("pol-"+k); if(el) body[k]=el.type==="number"?parseFloat(el.value):el.value} return body }
async function previewPolicy(btn){
  if(btn) btn.disabled=true;
  const el=$("policy-preview");
  try{ const d=await api("/api/v1/policy/preview",{method:"POST",body:JSON.stringify({policy:policyFormBody()})});
    if(!d.base_run_id){ el.innerHTML=`<div class="d" style="margin-top:10px">${esc(d.note||"No run to preview against.")}</div>`; return d }
    const movedH=d.moved_to_approvals||[], movedA=d.moved_to_auto||[];
    el.innerHTML=`<div class="hobanner" style="background:rgba(61,117,232,.14);border:1px solid var(--blue);padding:12px 14px;margin-top:12px"><b>Policy impact preview</b> - re-evaluated run ${esc(String(d.base_run_id).slice(0,13))}... with these values: auto-posted ${d.auto_before} &rarr; ${d.auto_after} (${money(d.posted_value_before_cents)} &rarr; ${money(d.posted_value_after_cents)}).
    ${movedH.length?`<div style="margin-top:6px"><b>${movedH.length} formerly auto-posted match${movedH.length>1?"es":""} (${money(movedH.reduce((a,m)=>a+m.amount_cents,0))}) move to Approvals Waiting:</b> ${movedH.map(m=>esc(m.payment_id)+" ("+money(m.amount_cents)+")").join(", ")}</div>`:""}
    ${movedA.length?`<div style="margin-top:6px"><b>${movedA.length} held match${movedA.length>1?"es":""} (${money(movedA.reduce((a,m)=>a+m.amount_cents,0))}) would auto-post:</b> ${movedA.map(m=>esc(m.payment_id)+" ("+money(m.amount_cents)+")").join(", ")}</div>`:""}
    ${!movedH.length&&!movedA.length?`<div style="margin-top:6px">No match changes decision under these values.</div>`:""}
    <div style="margin-top:6px"><small>${esc(d.note||"")}</small></div></div>`;
    return d;
  }catch(e){ el.innerHTML=`<div class="d" style="margin-top:10px">Preview failed: ${esc(e.message)}</div>` }
  finally{ if(btn) btn.disabled=false }
}
async function savePolicy(btn){
  btn.disabled=true;
  try{ await previewPolicy(null);
    const d=await api("/api/v1/policy",{method:"PUT",body:JSON.stringify({policy:policyFormBody()})});
    toast("Policy saved - the next batch run uses it (impact preview above)"); $("policy-src").textContent="Source: tenant (just saved)";
  }catch(e){toast("Save failed: "+e.message)}finally{btn.disabled=false}
}

async function loadMethod(){
  try{const d=await api("/api/v1/methodology");
    $("method-out").innerHTML=d.sections.map(sec=>`<div class="panel"><h3>${esc(sec.title)} <span data-info="methodsec"></span></h3><div class="d">${esc(sec.what)}</div>
    <table><tr><th style="width:230px">Component <span data-info="comp"></span></th><th>How it is computed <span data-info="howcomputed"></span></th></tr>${sec.formulae.map(f=>`<tr><td><b>${esc(f.name)}</b></td><td style="font-family:ui-monospace,Menlo,monospace;font-size:12.5px">${esc(f.expr)}</td></tr>`).join("")}</table>
    <p style="font-size:13.5px;line-height:1.6"><b>What it means:</b> ${esc(sec.meaning)}</p></div>`).join("");
  }catch(e){toast(e.message)}
}
let cbSeq=0;
function cbRow(id,cust,amt,po,age){
  cbSeq++;
  return `<div style="display:grid;grid-template-columns:1.1fr 1fr .8fr 1fr .6fr;gap:8px;margin-bottom:8px" class="cb-row">
  <input type="text" placeholder="Invoice ID" value="${id||("INV-"+cbSeq)}"><input type="text" placeholder="Customer" value="${cust||"Apex Manufacturing"}">
  <input type="number" placeholder="Amount $" value="${amt||""}"><input type="text" placeholder="PO (optional)" value="${po||""}">
  <input type="number" placeholder="Age days" value="${age||""}"></div>`;
}
function cbAddRow(id,cust,amt,po,age){$("cb-invs").insertAdjacentHTML("beforeend",cbRow(id,cust,amt,po,age))}
cbAddRow("INV-1","Apex Manufacturing",300,"PO-1",40); cbAddRow("INV-2","Apex Manufacturing",200,"PO-2",10); cbAddRow("INV-3","Apex Manufacturing",500,"PO-3",25);
async function cbRun(btn){
  const invs=[...document.querySelectorAll(".cb-row")].map(r=>{const i=r.querySelectorAll("input");return {invoice_id:i[0].value.trim(),customer:i[1].value.trim()||"UNKNOWN",gross_cents:Math.round(parseFloat(i[2].value||0)*100),po_number:i[3].value.trim()||null,age_days:parseInt(i[4].value||0)}}).filter(x=>x.invoice_id&&x.gross_cents>0);
  const refs=$("cb-refs").value.split(",").map(x=>x.trim()).filter(Boolean);
  const pay={payment_id:"CUSTOM-1",payer_raw:$("cb-payer").value.trim()||"UNKNOWN",amount_cents:Math.round(parseFloat($("cb-amount").value||0)*100),references:refs,claimed_deduction_cents:Math.round(parseFloat($("cb-ded").value||0)*100),deduction_reason_raw:$("cb-reason").value,pod_verified_clean:$("cb-pod").checked,remittance_text:"Custom case from the builder"};
  if(!invs.length){toast("Add at least one invoice with an amount");return}
  btn.disabled=true;
  try{const d=await api("/api/v1/workspace/load-custom",{method:"POST",body:JSON.stringify({invoices:invs,payments:[pay]})});
    WS=d.workspace; casePayments=d.payments; seedPayments=d.payments; renderCasebar();
    $("cb-out").innerHTML=`<div class="msg">Your case is now the active case in the shared workspace: <b>${invs.length} invoices and 1 payment staged</b>. Taking you to Run Reconciliation - run it there and open the match for its full derivation.</div>`;
    toast("Custom case loaded into the workspace"); setTimeout(()=>go("run"),650);
  }catch(e){toast("Case failed: "+e.message)}finally{btn.disabled=false}
}
const LOADERS={dash:refreshDash,ledger:loadLedger,forecast:loadForecast,eval:loadEval,health:async()=>{await loadHealth();await loadAudit()},cases:loadCases,policy:loadPolicy,method:loadMethod,arch:loadDiag,run:async()=>{await refreshWorkspace();await renderGradeFromStored();await loadApprovals()},upload:async()=>{await refreshWorkspace();loadAiStrip();wireAutoParse()}};
async function runLive(btn){
  btn.disabled=true; btn.textContent="Running...";
  const out=$("live-out");
  await refreshWorkspace();
  if(!WS||!WS.staged_payments){
    out.innerHTML=`<div class="verdict fail">Nothing staged to run. Load a case first - the demo case, a use case, the builder, or your uploaded payments - then run it here, live.</div>`;
    btn.disabled=false; btn.textContent="Run the active case live"; return;
  }
  // When every staged payment has already been run, the stream replays
  // the case's full batch (the backend's workspace fallback), so the
  // live lanes are never a dead end on an already-run case.
  out.innerHTML=`<div class="grid2" style="align-items:start"><div id="live-lanes"></div><div id="live-log"></div></div><div id="live-summary" style="margin-top:10px"></div>`;
  const lanes=$("live-lanes"), log=$("live-log"), lanesById={};
  const t0=performance.now();
  const stamp=()=>(((performance.now()-t0)/1000).toFixed(2)+"s").padStart(6," ");
  const logLine=(html)=>{log.innerHTML+=`<div><span class="t">${stamp()}</span> ${html}</div>`; log.scrollTop=log.scrollHeight};
  const chip=(lane,i,state,label)=>{const c=lane.querySelectorAll(".chip")[i]; if(!c)return; c.className="chip "+state; if(label)c.innerHTML=label};
  try{
    const res=await fetch("/api/v1/runs/stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({use_workspace:true})});
    if(!res.ok||!res.body) throw new Error("stream failed: "+res.status);
    const reader=res.body.getReader(), dec=new TextDecoder(); let buf="";
    while(true){
      const {done,value}=await reader.read(); if(done)break;
      buf+=dec.decode(value,{stream:true});
      let idx; while((idx=buf.indexOf("\n\n"))>=0){
        const raw=buf.slice(0,idx); buf=buf.slice(idx+2);
        if(!raw.startsWith("data: ")) continue;
        const e=JSON.parse(raw.slice(6));
        if(e.type==="batch_start"){logLine(`<span class="hl">BATCH</span> ${e.run_id} - ${e.payments} payments`)}
        else if(e.type==="payment_start"){
          const lane=document.createElement("div"); lane.className="lane";
          lane.innerHTML=`<div class="who"><b>${esc(e.payment_id)}</b> - ${esc(e.payer)}<small>${money(e.amount_cents)}</small></div><div class="stages"><span class="chip">1 RESOLVE</span><span class="chip">2 SOLVE</span><span class="chip">3 DEDUCTION</span><span class="chip">4 DECISION</span></div>`;
          lanes.appendChild(lane); lanesById[e.payment_id]=lane;
          logLine(`${e.payment_id} received - ${money(e.amount_cents)} from ${esc(e.payer)}`);
        }
        else if(e.type==="resolved"){chip(lanesById[e.payment_id],0,"done",`1 RESOLVED - ${esc(e.matched_by)} - ${e.candidates} candidate${e.candidates==1?"":"s"}`); logLine(`${e.payment_id} Linking Agent narrowed candidates by <span class="hl">${esc(e.matched_by)}</span> to ${e.candidates}`)}
        else if(e.type==="solved"){const L=lanesById[e.payment_id]; chip(L,1,e.status==="OPTIMAL_EXACT_MATCH"?"done":"on",`2 SOLVED - ${esc(e.status)} - ${e.latency_ms} ms`); if(!e.invoices.length) chip(L,2,"","3 NO DEDUCTION"); logLine(`${e.payment_id} Matching Agent: ${esc(e.status)}, residual ${money(e.residual_cents)}, confidence ${Number(e.confidence).toFixed(2)}, ${e.latency_ms} ms`)}
        else if(e.type==="deduction"){chip(lanesById[e.payment_id],2,"on",`3 DEDUCTION - ${esc(e.decision||"judged")} ${esc(e.reason_code||"")}`); logLine(`${e.payment_id} Deduction Agent judged: <span class="hl">${esc(e.decision||"")}</span> (${esc(e.reason_code||"")}), z ${e.z_score}, expected recovery $${e.expected_recovery}`)}
        else if(e.type==="decision"){const L=lanesById[e.payment_id]; if(L){const c3=L.querySelectorAll(".chip")[2]; if(c3&&c3.textContent.includes("DEDUCTION")&&!c3.className.includes("on")&&!c3.className.includes("done")) c3.innerHTML="3 NO CLAIM"; chip(L,3,e.decision==="AUTO_POSTED"?"done":(e.decision==="EXCEPTION"?"bad":"on"),`4 ${esc(e.decision)}`)} logLine(`${e.payment_id} Policy Agent decision: <span class="${e.decision==="AUTO_POSTED"?"ok":(e.decision==="EXCEPTION"?"bad":"hl")}">${esc(e.decision)}</span> - ${esc(e.reason)}`)}
        else if(e.type==="batch_done"){$("live-summary").innerHTML=`<div class="verdict pass">Run ${e.run_id} complete: ${e.auto_posted} of ${e.payments} auto-posted, touchless ${Math.round(100*e.auto_posted/Math.max(e.payments,1))}% - total engine time ${e.ms} ms. Stored - see it in Dashboard run history.</div>`; logLine(`<span class="ok">DONE</span> ${e.run_id} in ${e.ms} ms`)}
        else if(e.type==="error"){logLine(`<span class="bad">ERROR</span> ${esc(e.message)}`)}
      }
    }
  }catch(err){out.innerHTML=`<div class="verdict fail">Live stream failed: ${esc(err.message)}. The stored-run path still works - use Run without streaming.</div>`}
  btn.disabled=false; btn.textContent="Run the active case live";
  try{
    const ws2=await refreshWorkspace();
    if(ws2&&ws2.latest_run){
      const [m,x]=await Promise.all([api(`/api/v1/runs/${ws2.latest_run.run_id}/matches`),api(`/api/v1/runs/${ws2.latest_run.run_id}/exceptions`)]);
      renderStoredRun(ws2.latest_run.run_id,m,x); await renderGradeFromStored();
    }
    refreshDash();
  }catch(e){}
  scheduleApprovalsJump(1000);
}
let __apprN=0;
async function loadApprovals(){
  const out=$("appr-out"); if(!out)return 0;
  try{
    const list=await api("/api/v1/approvals");
    const badge=$("appr-count");
    if(badge){badge.style.display=list.length?"":"none"; badge.textContent=list.length+" waiting"}
    __apprN=list.length;
    out.innerHTML=list.length?`<table><tr><th>Payment <span data-info="payid"></span></th><th>Amount <span data-info="amt"></span></th><th>Matched invoices <span data-info="lines"></span></th><th>Conf. <span data-info="conf"></span></th><th>Why it is held <span data-info="held"></span></th><th>Decision <span data-info="apprdec"></span></th></tr>${list.map(a=>`<tr><td>${esc(a.payment_id)}<br><small>${esc(a.run_id)}</small></td><td>${a.amount_cents==null?"-":money(a.amount_cents)}</td><td>${a.invoices.map(esc).join(", ")||"-"}</td><td>${Number(a.confidence).toFixed(2)}</td><td style="max-width:340px">${esc(a.decision_reason||"Held for review")}</td><td style="white-space:nowrap"><button class="btn small" onclick="decideMatch('${a.match_id}','approve',this)">Approve and post</button> <button class="btn small ghost" onclick="decideMatch('${a.match_id}','reject',this)">Reject</button></td></tr>`).join("")}</table>`:"<small>Nothing waiting. Matches appear here when policy holds one - lower the maker-checker threshold in Policy Studio and run a batch to see it work.</small>";
  }catch(e){out.innerHTML=`<small>Could not load approvals: ${esc(e.message)}</small>`}
  return __apprN;
}
let __apprTimer=null;
async function scheduleApprovalsJump(ms){
  // After the run's mechanism is on screen, glide to the approvals queue on
  // the same page so held matches are never missed. Manual scrolling cancels.
  __apprN=await loadApprovals();
  if(!__apprN)return;
  clearTimeout(__apprTimer);
  const cancel=()=>{clearTimeout(__apprTimer);window.removeEventListener("wheel",cancel);window.removeEventListener("touchstart",cancel)};
  window.addEventListener("wheel",cancel,{passive:true}); window.addEventListener("touchstart",cancel,{passive:true});
  __apprTimer=setTimeout(()=>{cancel();const p=document.getElementById("approvals-panel");if(!p)return;
    p.scrollIntoView({behavior:"smooth",block:"start"});
    p.classList.remove("flash"); void p.offsetWidth; p.classList.add("flash");
    toast(__apprN+(__apprN===1?" match is":" matches are")+" waiting for approval - this queue lives on this page, below the matches");
  },ms);
}
async function decideMatch(id,decision,btn){
  btn.disabled=true;
  try{const r=await api("/api/v1/matches/"+id+"/decision",{method:"POST",body:JSON.stringify({decision})});
    BRIEF_RUN=null; BRIEF_PROMISE=null;
    let msg=(decision==="approve"?"Match approved and posted":"Match rejected");
    if(decision==="approve"&&r.erp_document_id) msg+=` - ERP document ${r.erp_document_id}`;
    if(decision==="approve"&&(r.settled_invoices||[]).length) msg+=` - ${r.settled_invoices.length} invoice(s) settled and out of the forecast`;
    if(r.fingerprint) msg+=` - audit fingerprint ${r.fingerprint.slice(0,12)}...`;
    toast(msg);
    loadApprovals(); if($("appr-drawer").classList.contains("on")) renderApprDrawer();
    const w=await refreshWorkspace(); if(w) refreshDash();}
  catch(e){toast("Decision failed: "+e.message); btn.disabled=false}
}
/* ---- v9: connectivity - drawer, run diff, handoffs, forecast disputes ---- */
function openApprovals(){ openApprDrawer(); }
async function openApprDrawer(){
  $("appr-drawer").classList.add("on"); $("drawer-scrim").classList.add("on");
  renderApprDrawer();
}
function closeApprDrawer(){ $("appr-drawer").classList.remove("on"); $("drawer-scrim").classList.remove("on"); }
async function renderApprDrawer(){
  const el=$("drawer-list"); if(!el) return;
  try{ const list=await api("/api/v1/approvals");
    el.innerHTML=list.length?list.map(a=>`<div class="deskcard"><b>${esc(a.payment_id)}</b> - ${a.amount_cents==null?"-":money(a.amount_cents)} - invoices ${a.invoices.map(esc).join(", ")||"-"}<br><small>${esc(a.decision_reason||"Held for review")}</small><div style="margin-top:8px"><button class="btn small" onclick="decideMatch('${a.match_id}','approve',this)">Approve and post</button> <button class="btn small ghost" onclick="decideMatch('${a.match_id}','reject',this)">Reject</button></div></div>`).join(""):"<small>Nothing waiting. When policy holds a match it appears here, on every page.</small>";
  }catch(e){ el.innerHTML=`<small>Could not load approvals: ${esc(e.message)}</small>` }
}
let DIFFSEL={cur:null,prev:null};
async function toggleRunDiff(){
  const el=$("run-diff");
  if(el.style.display!=="none"&&el.innerHTML){ el.style.display="none"; return }
  el.style.display="block"; el.innerHTML="<small>Loading run comparison...</small>";
  try{ const runs=await api("/api/v1/runs");
    if(runs.length<2){ el.innerHTML=`<b>Run comparison</b><div class="d" style="margin-top:6px">${runs.length?"Only one run exists so far - run the batch again (or load another case and run it) and this compares the two.":"No runs yet - load a case and run the batch first."}</div>`; return }
    DIFFSEL={cur:runs[0].run_id, prev:runs[1].run_id};
    await renderRunDiff(runs);
  }catch(e){ el.innerHTML=`<small>${esc(e.message)}</small>` }
}
async function renderRunDiff(runs){
  const el=$("run-diff");
  try{
  runs=runs||await api("/api/v1/runs");
  const cur=runs.find(r=>r.run_id===DIFFSEL.cur)||runs[0]; const prev=runs.find(r=>r.run_id===DIFFSEL.prev)||runs[1];
  const opt=sel=>runs.map(r=>`<option value="${r.run_id}" ${r.run_id===sel?"selected":""}>${esc(r.run_id.slice(0,13))}... - ${esc(r.created_at||"").slice(5,16).replace("T"," ")}</option>`).join("");
  const [mc,mp,xc,xp]=await Promise.all([api(`/api/v1/runs/${cur.run_id}/matches`),api(`/api/v1/runs/${prev.run_id}/matches`),api(`/api/v1/runs/${cur.run_id}/exceptions`),api(`/api/v1/runs/${prev.run_id}/exceptions`)]);
  const stp=r=>r.payments?Math.round(1000*r.auto_posted/r.payments)/10:0;
  const d=stp(cur)-stp(prev); const dEl=d>0?`<span class="diffup">+${d.toFixed(1)} pts</span>`:d<0?`<span class="diffdn">${d.toFixed(1)} pts</span>`:"no change";
  const before={}; mp.forEach(m=>before[m.payment_id]=m.status); const after={}; mc.forEach(m=>after[m.payment_id]=m.status);
  const changes=Object.keys(after).filter(pid=>before[pid]&&before[pid]!==after[pid]).map(pid=>`<tr><td>${esc(pid)}</td><td>${esc(before[pid])}</td><td>${esc(after[pid])}</td></tr>`).join("");
  el.innerHTML=`<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><b>Run comparison</b><label><small>Current</small> <select onchange="DIFFSEL.cur=this.value;renderRunDiff()">${opt(cur.run_id)}</select></label><label><small>Previous</small> <select onchange="DIFFSEL.prev=this.value;renderRunDiff()">${opt(prev.run_id)}</select></label><button class="btn small ghost" onclick="toggleRunDiff()">Close</button></div>
  <div class="cards" style="grid-template-columns:repeat(4,minmax(0,1fr));margin:12px 0 4px">
  <div class="card"><div class="k">Straight-through rate</div><div class="v">${stp(prev)}% → ${stp(cur)}%</div><div class="n">${dEl} between these two runs</div></div>
  <div class="card"><div class="k">Auto-posted</div><div class="v">${prev.auto_posted} → ${cur.auto_posted}</div><div class="n">of ${prev.payments} → ${cur.payments} payments</div></div>
  <div class="card"><div class="k">Exceptions</div><div class="v">${xp.length} → ${xc.length}</div><div class="n">payments the agent refused to guess on</div></div>
  <div class="card"><div class="k">Decision changes</div><div class="v">${changes?Object.keys(after).filter(pid=>before[pid]&&before[pid]!==after[pid]).length:0}</div><div class="n">payments whose decision differs between the runs</div></div></div>
  ${changes?`<table><tr><th>Payment</th><th>Previous decision</th><th>Current decision</th></tr>${changes}</table>`:"<small>No payment changed decision between these two runs.</small>"}`;
  }catch(e){ el.innerHTML=`<b>Run comparison</b><div class="d" style="margin-top:6px">Could not compare those runs: ${esc(e.message)}</div>` }
}
function showHandoff(){
  const el=$("handoff"); if(!el||!WS) return;
  const p=WS.pending_payments||[];
  if(!p.length){ el.innerHTML=""; return }
  const tot=p.reduce((a,x)=>a+(x.amount_cents||0),0);
  el.innerHTML=`<div class="hobanner"><span>&#10003; <b>${p.length} payment${p.length>1?"s":""} staged (${money(tot)})</b> - ready to reconcile.</span><button class="btn" onclick="gotoRunStaged()">Execute reconciliation &rarr;</button><small>The staged payments are highlighted at the top of the Run page.</small></div>`;
}
function gotoRunStaged(){
  go("run");
  setTimeout(()=>{ const box=$("staged-box"); if(!box) return;
    const ids=new Set((WS.pending_payments||[]).map(p=>p.payment_id));
    box.querySelectorAll("table tr").forEach(tr=>{ const td=tr.querySelector("td"); if(td&&ids.has(td.textContent.trim())) tr.classList.add("hlrow"); });
    box.scrollIntoView({behavior:"smooth",block:"center"});
  },420);
}
async function renderFcDisputes(){
  const el=$("fc-disputes"); if(!el) return;
  try{ const ws=WS||await refreshWorkspace(); if(!ws||!ws.latest_run){ el.innerHTML=""; return }
    const ms=await api(`/api/v1/runs/${ws.latest_run.run_id}/matches`);
    const claims=ms.map(m=>({m, d:(m.result||{}).deduction})).filter(x=>x.d&&x.d.autonomous_action==="AUTO_GENERATE_DISPUTE_CLAIM")
      .sort((a,b)=>Number(b.d.expected_recovery_value_usd||0)-Number(a.d.expected_recovery_value_usd||0));
    if(!claims.length){ el.innerHTML=""; return }
    el.innerHTML=`<div class="panel"><h3>Dispute priority - from the active run</h3><div class="d">The Deduction Agent flagged these short-pays during reconciliation. They sit at the top of the collections work because the money is recoverable: expected recovery is win probability x claim, minus the cost of fighting. One click takes you to the claim on the Dispute desk, draft ready.</div>
    <table><tr><th>Payment</th><th>Payer</th><th>Claim</th><th>Reason</th><th>Win probability</th><th>Expected recovery</th><th></th></tr>${claims.map(({m,d})=>`<tr><td>${esc(m.payment_id)}</td><td>${esc(d.payer||"")}</td><td>${money(d.claimed_cents||0)}</td><td>${esc(d.assigned_erp_reason_code||"")} - ${esc((d.classification||{}).label||"deduction")}</td><td>${d.win_probability}</td><td><b>$${Number(d.expected_recovery_value_usd||0).toLocaleString("en-US",{maximumFractionDigits:2})}</b></td><td><button class="btn small" onclick="dispatchClaim('${esc(m.payment_id)}')">Dispatch dispute email &rarr;</button></td></tr>`).join("")}</table></div>`;
  }catch(e){}
}
async function dispatchClaim(pid){
  const ws=WS||await refreshWorkspace(); if(!ws||!ws.latest_run){ toast("No run yet - nothing to dispatch"); return }
  await openRun(ws.latest_run.run_id);
  setTimeout(()=>{ const i=(typeof DESK!=="undefined"?DESK:[]).findIndex(f=>f.payment_id===pid);
    const card=document.querySelectorAll(".deskcard")[i<0?0:i];
    if(card){ card.scrollIntoView({behavior:"smooth",block:"center"}); card.classList.remove("flashcard"); void card.offsetWidth; card.classList.add("flashcard"); const inp=card.querySelector("input"); if(inp) inp.focus(); }
  },650);
}
async function loadAudit(){
  const out=$("audit-out"); if(!out)return;
  try{
    const list=await api("/api/v1/audit");
    out.innerHTML=list.length?`<table><tr><th>When (UTC) <span data-info="when"></span></th><th>Actor <span data-info="actor"></span></th><th>Action <span data-info="action"></span></th><th>Record <span data-info="rec"></span></th><th>Detail <span data-info="detail"></span></th></tr>${list.slice(0,30).map(a=>`<tr><td style="white-space:nowrap">${esc(String(a.created_at).replace("T"," ").slice(0,19))}</td><td>${esc(a.actor)}</td><td><span class="pill info">${esc(a.action)}</span></td><td>${esc(a.entity)} ${esc(a.entity_id)}</td><td><small>${esc(JSON.stringify(a.payload))}</small></td></tr>`).join("")}</table>`:"<small>No audit entries yet. Run a batch to create the first one.</small>";
  }catch(e){out.innerHTML=`<small>Could not load audit trail: ${esc(e.message)}</small>`}
}
async function loadAiStrip(){
  const el=$("ai-strip"); if(!el)return;
  try{
    const h=await api("/health");
    el.innerHTML=h.gemini_configured
      ?`<b style="color:var(--ok)">Gemini extraction is LIVE.</b> Every parse below is read by the AI model, then verified against the ledger before anything is trusted.`
      :`<b style="color:var(--warn)">Deterministic mode.</b> No Gemini key is configured on this server, so a fixed-rule extractor is reading the text - and it is labelled as such on every result. Add a server-side GEMINI_API_KEY and the same pipeline switches to live AI extraction with no other change: the schema check and the ledger verification you see below are identical in both modes.`;
  }catch(e){el.textContent="Could not check the AI layer status."}
}

/* ---- v4: AI in the workflow - staging, briefs, dispute desk, impact, cube ---- */
let LAST_PARSE=null;
function renderWireCard(){
  const f=(LAST_PARSE&&LAST_PARSE.fields)||{};
  $("wire-amt").textContent=f.amount_cents?money(f.amount_cents):"not parsed yet";
  $("wire-meta").innerHTML=`Payer: <b>${esc(f.payer||"-")}</b> - read by <b>${esc(LAST_PARSE.source||"deterministic")}</b>${LAST_PARSE.degraded?" (deterministic fallback - no Gemini key configured)":""} - ${(LAST_PARSE.verification||{}).verified?'<span style="color:var(--ok)">every reference verified in the ledger</span>':'<span style="color:var(--warn)">some references flagged - see the pipeline below</span>'}`;
  $("wire-ded").innerHTML=f.deduction_cents?`<div class="dedcard">Claimed deduction: <b>-${money(f.deduction_cents)}</b>${f.deduction_reason?` - ${esc(f.deduction_reason)}`:""} - the Deduction Agent classifies it at reconcile time, and the expected-value rule decides whether to dispute it.</div>`:"";
  const ok=f.amount_cents>0; $("stage-btn").disabled=!ok; $("stage-run-btn").disabled=!ok;
}
async function stageParsed(btn){
  if(!LAST_PARSE) return null;
  const f=LAST_PARSE.fields||{}; btn.disabled=true;
  try{
    const refs=[...(f.invoice_refs||[]),...(f.po_refs||[])];
    const out=await api("/api/v1/workspace/stage-payment",{method:"POST",body:JSON.stringify({payer:f.payer||"",amount_cents:f.amount_cents||0,references:refs,claimed_deduction_cents:f.deduction_cents||0,deduction_reason:f.deduction_reason||"",remittance_text:$("parse-in").value})});
    await refreshWorkspace(); renderUpStaged();
    toast("Wire staged as "+out.staged+" - find it in Run Reconciliation");
    return out;
  }catch(e){toast(e.message); return null} finally{btn.disabled=false}
}
async function stageAndRun(btn){ const out=await stageParsed(btn); if(out){ go("run"); const b=$("live-btn"); if(b) runLive(b); } }
async function loadBrief(runId){
  const el=$("run-brief"); if(!el) return;
  try{
    const b=await api(`/api/v1/runs/${runId}/brief`);
    el.innerHTML=`<div class="panel"><h3>Agent brief - run ${esc(runId)} <span data-info="brief"></span></h3><div class="detail"><b>${esc(b.headline)}</b>${(b.body||[]).map(x=>`<br>${esc(x)}`).join("")}<br><br><b>Next actions:</b><br>${(b.next_actions||[]).map(a=>"· "+esc(a)).join("<br>")}<br><br>${pill(b.source==="gemini"?"Written by Gemini from run records":"Composed from run records - Gemini not configured","info")}</div></div>`;
  }catch(e){ el.innerHTML="" }
}
let DESK=[];
function deskCard(f,i){
  return `<div class="deskcard"><b>${esc(f.payment_id)}</b> - ${esc(f.payer)} - claim <b>${money(f.claimed_cents)}</b> - ${esc(f.reason_code)} (${esc(f.classification_label)}) - win probability ${f.win_probability} - expected recovery $${Number(f.expected_recovery_usd).toFixed(2)}
  <div class="tonebar"><button data-tone="strict" class="on" onclick="deskTone(${i},'strict',this)">Strict Audit</button><button data-tone="contract" onclick="deskTone(${i},'contract',this)">Contract Cap</button><button data-tone="escalate" onclick="deskTone(${i},'escalate',this)">VP Escalate</button><button onclick="deskDraft(${i},this)">Draft claim email</button></div>
  <textarea id="desk-text-${i}" rows="9" placeholder="The claim draft appears here - editable before you send or copy it."></textarea>
  <p><button class="btn small ghost" onclick="copyDesk(${i})">Copy draft</button> <span id="desk-src-${i}"></span></p>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><input id="desk-to-${i}" placeholder="Buyer AP email - e.g. ap@buyer.com" style="flex:1;min-width:200px"><button class="btn small" onclick="sendDeskMail(${i},this)">Send claim</button><span id="desk-mail-${i}"></span></div>
  <div class="tonebar"><span style="align-self:center"><small>Simulate buyer reply:</small></span><button onclick="deskRebuttal(${i},'damage',this)">Concealed damage</button><button onclick="deskRebuttal(${i},'discount_timing',this)">Discount timing</button><button onclick="deskRebuttal(${i},'split',this)">Offers 50% split</button></div>
  <textarea id="desk-reb-${i}" rows="5" placeholder="The rebuttal draft appears here. The 50% split answer is computed from this claim's expected value."></textarea>
  <p><button class="btn small ghost" onclick="copyDeskReb(${i})">Copy rebuttal</button> <span id="desk-reb-src-${i}"></span></p></div>`;
}
let CHASE=[];
function chaseCard(f,i){
  return `<div class="deskcard"><b>${esc(f.payment_id)}</b> - ${esc(f.payer)} - <b>${money(f.amount_cents)}</b> arrived with no remittance and matched nothing on their account.
  <div class="tonebar"><button onclick="chaseDraft(${i},this)">Draft chase email</button></div>
  <textarea id="chase-text-${i}" rows="9" placeholder="The chase draft appears here - it asks the payer for the remittance advice and confirms the amount stays unapplied meanwhile."></textarea>
  <p><button class="btn small ghost" onclick="copyChase(${i})">Copy draft</button> <span id="chase-src-${i}"></span></p>
  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><input id="chase-to-${i}" placeholder="Payer AP email - e.g. ap@payer.com" style="flex:1;min-width:200px"><button class="btn small" onclick="sendChaseMail(${i},this)">Send chase</button><span id="chase-mail-${i}"></span></div></div>`;
}
async function chaseDraft(i,btn){
  btn.disabled=true;
  try{ const d=await api("/api/v1/ai/draft",{method:"POST",body:JSON.stringify({kind:"chase_email",tone:"strict",facts:CHASE[i]})});
    $("chase-text-"+i).value=d.text;
    $("chase-src-"+i).innerHTML=pill(d.source==="gemini"?"Written by Gemini":"Grounded template - Gemini not configured","info");
  }catch(e){toast(e.message)} finally{btn.disabled=false}
}
function copyChase(i){ navigator.clipboard.writeText($("chase-text-"+i).value).then(()=>toast("Chase draft copied")) }
async function renderDisputeDesk(matches, exceptions){
  const el=$("dispute-desk"); if(!el) return;
  let ms=matches, xs=exceptions;
  if(!ms){ const ws=await refreshWorkspace(); if(!ws||!ws.latest_run){ el.innerHTML=""; return } ms=await api(`/api/v1/runs/${ws.latest_run.run_id}/matches`); xs=await api(`/api/v1/runs/${ws.latest_run.run_id}/exceptions`); }
  const items=(ms||[]).filter(m=>{const d=(m.result||{}).deduction; return d&&d.autonomous_action==="AUTO_GENERATE_DISPUTE_CLAIM"});
  CHASE=(xs||[]).filter(e=>e.kind==="NO_MATCH").map(e=>({payment_id:e.payment_id,payer:(e.detail||{}).payer||"Unknown payer",amount_cents:(e.detail||{}).amount_cents||0}));
  if(!items.length && !CHASE.length){ el.innerHTML=""; return }
  DESK=items.map(m=>{const d=m.result.deduction; return {payment_id:m.payment_id,payer:d.payer||"Buyer",claimed_cents:d.claimed_cents||0,reason_code:d.assigned_erp_reason_code,classification_label:(d.classification||{}).label||"deduction",win_probability:d.win_probability,expected_recovery_usd:d.expected_recovery_value_usd,tone:"strict"}});
  el.innerHTML=`<div class="panel"><h3>Dispute desk - deductions worth fighting <span data-info="dispute"></span></h3><div class="d">The Deduction Agent classified these claims and the expected-value rule opened disputes. The Briefing Agent drafts the claim and the replies - review the draft, add the buyer's AP email, and send it from here. Every send is recorded in the Outbox below with its true status.</div>${DESK.map((f,i)=>deskCard(f,i)).join("")}${CHASE.length?`<h3 style="margin-top:18px">Unmatched payments - chase the remittance</h3><div class="d">These payments matched nothing, so the cash sits unapplied. The platform does not guess: it asks the payer which invoices the money was for. Draft the chase email here and send it from here.</div>${CHASE.map((f,i)=>chaseCard(f,i)).join("")}`:""}<div id="outbox-strip"></div></div>`;
  loadOutbox();
}
function splitSubject(text){
  const t=(text||"").trim();
  const m=t.match(/^Subject:\s*(.+)\n\n?/);
  if(m) return {subject:m[1].trim(), body:t.slice(m[0].length).trim()};
  const lines=t.split("\n"); return {subject:(lines[0]||"").slice(0,120), body:t};
}
async function sendMailGeneric(kind, refId, to, rawText, statusId, btn, presetSubject){
  const el=$(statusId); if(!to||!to.trim()){ toast("Add the recipient's email first"); return }
  let subject, body;
  if(presetSubject!==undefined){ subject=presetSubject; body=rawText; }
  else { const s=splitSubject(rawText); subject=s.subject; body=s.body; }
  if(!body){ toast("Draft the message first"); return }
  btn.disabled=true;
  try{ const r=await api("/api/v1/mail/send",{method:"POST",body:JSON.stringify({to:to.trim(),subject,body,kind,ref_id:refId})});
    if(el) el.innerHTML=pill(r.status==="sent"?"Sent":r.status==="failed"?"Send failed - see Outbox":"Recorded - not sent (no mailbox configured)", r.status==="sent"?"ok":r.status==="failed"?"bad":"warn");
    toast(r.status==="sent"?"Mail sent":r.status==="failed"?"Send failed - recorded in the Outbox":"Recorded in the Outbox - no mailbox configured, nothing was sent");
    loadOutbox();
  }catch(e){ toast(e.message) } finally{ btn.disabled=false }
}
function sendDeskMail(i,btn){ sendMailGeneric("dispute_claim", DESK[i].payment_id, $("desk-to-"+i).value, $("desk-text-"+i).value, "desk-mail-"+i, btn) }
function sendChaseMail(i,btn){ sendMailGeneric("chase", CHASE[i].payment_id, $("chase-to-"+i).value, $("chase-text-"+i).value, "chase-mail-"+i, btn) }
async function loadOutbox(){
  const el=$("outbox-strip"); if(!el) return;
  try{ const o=await api("/api/v1/mail/outbox");
    el.innerHTML=`<h3 style="margin-top:18px">Outbox</h3><div class="d">${o.configured?pill("Mailbox configured - sends go out from "+esc(o.from),"ok"):pill("No mailbox configured - sends are recorded, not sent","warn")} Every send from this product is recorded here with its true status - a mail is only ever shown as sent when the mail server accepted it.</div>`+(o.mails.length?`<table><tr><th>When (UTC)</th><th>To</th><th>Subject</th><th>Kind</th><th>Status</th></tr>${o.mails.slice(0,10).map(m=>`<tr><td>${esc((m.created_at||"").slice(5,16).replace("T"," "))}</td><td>${esc(m.to)}</td><td>${esc(m.subject)}</td><td>${esc(m.kind)}</td><td>${pill(m.status==="sent"?"Sent":m.status==="failed"?"Failed":"Recorded - not sent", m.status==="sent"?"ok":m.status==="failed"?"bad":"warn")}</td></tr>`).join("")}</table>`:"<small>Nothing sent yet.</small>");
  }catch(e){}
}
function deskTone(i,t,btn){ DESK[i].tone=t; btn.parentElement.querySelectorAll("button[data-tone]").forEach(b=>b.classList.toggle("on",b===btn)); }
async function deskDraft(i,btn){
  btn.disabled=true;
  try{ const d=await api("/api/v1/ai/draft",{method:"POST",body:JSON.stringify({kind:"dispute_email",tone:DESK[i].tone,facts:DESK[i]})});
    $("desk-text-"+i).value=d.text;
    $("desk-src-"+i).innerHTML=pill(d.source==="gemini"?"Written by Gemini":"Grounded template - Gemini not configured","info");
  }catch(e){toast(e.message)} finally{btn.disabled=false}
}
async function deskRebuttal(i,kind,btn){
  const f=DESK[i]; const facts={...f,buyer_reply:kind,offer_usd:kind==="split"?Math.round(f.claimed_cents/2)/100:0};
  btn.disabled=true;
  try{ const d=await api("/api/v1/ai/draft",{method:"POST",body:JSON.stringify({kind:"rebuttal",tone:f.tone,facts})});
    $("desk-reb-"+i).value=d.text;
    $("desk-reb-src-"+i).innerHTML=pill(d.source==="gemini"?"Written by Gemini":"Grounded template - Gemini not configured","info");
  }catch(e){toast(e.message)} finally{btn.disabled=false}
}
function copyDesk(i){ navigator.clipboard.writeText($("desk-text-"+i).value).then(()=>toast("Claim draft copied")) }
function copyDeskReb(i){ navigator.clipboard.writeText($("desk-reb-"+i).value).then(()=>toast("Rebuttal copied")) }
async function renderImpact(){
  const el=$("impact-body"); if(!el) return;
  try{
    const runs=await api("/api/v1/runs"); if(!runs.length){ el.innerHTML=""; return }
    let cash=0, auto=0, totLines=0, autoLines=0, rec=0;
    for(const r of runs.slice(0,5)){
      const ms=await api(`/api/v1/runs/${r.run_id}/matches`);
      for(const m of ms){ const res=m.result||{}; const lines=res.lines||[]; totLines+=lines.length;
        if(res.auto_posted||m.status==="APPROVED_POSTED"){ auto++; autoLines+=lines.length; cash+=lines.reduce((a,l)=>a+l.net_cents,0); }
        const d=res.deduction||{}; if(d.autonomous_action==="AUTO_GENERATE_DISPUTE_CLAIM") rec+=Number(d.expected_recovery_value_usd||0); }
    }
    const lineRate=totLines?Math.round(100*autoLines/totLines):0;
    el.innerHTML=`<div class="cards" style="grid-template-columns:repeat(4,1fr)"><div class="card"><div class="k">Cash posted by the agent</div><div class="v">${money(cash)}</div><div class="n">Net applied on auto-posted matches across the last ${Math.min(runs.length,5)} runs</div></div><div class="card"><div class="k">Analyst hours returned</div><div class="v">${(auto*12/60).toFixed(1)} h</div><div class="n">${auto} auto-posted payments x 12 minutes manual benchmark (a labelled assumption)</div></div><div class="card"><div class="k">Invoice-line touchless</div><div class="v">${lineRate}%</div><div class="n">Lines posted with no human touch, of all matched lines. The market median auto-match rate is 70% (Hackett, 2025) - the line to beat</div></div><div class="card"><div class="k">Recovery in flight</div><div class="v">$${rec.toLocaleString("en-US",{maximumFractionDigits:0})}</div><div class="n">Expected value of the dispute claims the agent has opened</div></div></div>`;
  }catch(e){}
}
function renderCube(inv){
  const el=$("cube-out"); if(!el) return;
  if(!inv||!inv.length){ el.innerHTML=""; return }
  const by={}; inv.forEach(i=>{ const b=by[i.customer]=by[i.customer]||{n:0,total:0,over:0}; b.n++; b.total+=i.gross_cents; if(i.due_in_days<0) b.over+=i.gross_cents; });
  const rows=Object.entries(by).sort((a,b)=>b[1].total-a[1].total);
  el.innerHTML=`<div class="panel"><h3>Cube view - open AR by customer <span data-info="cube"></span></h3><table><tr><th>Customer <span data-info="cust"></span></th><th>Open invoices <span data-info="invid"></span></th><th>Open AR <span data-info="amt"></span></th><th>Overdue <span data-info="due"></span></th></tr>${rows.map(([c,v])=>`<tr><td>${esc(c)}</td><td>${v.n}</td><td>${money(v.total)}</td><td>${money(v.over)}</td></tr>`).join("")}</table></div>`;
}
/* ---- Serro-pass 2: live status bar, command palette, reveal, count-up ---- */
async function loadStatusBar(){
  try{
    const h=await api("/health");
    $("sb-dot").classList.toggle("bad",h.status!=="ok");
  }catch(e){ $("sb-dot").classList.add("bad"); }
}
loadStatusBar(); setInterval(loadStatusBar,60000);

const __rvObs=("IntersectionObserver" in window)?new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){e.target.classList.add("rvin");__rvObs.unobserve(e.target)}})},{threshold:.06}):null;
function initReveal(){
  if(!__rvObs)return;
  const sec=document.querySelector("main section.active"); if(!sec)return;
  sec.querySelectorAll(".panel:not(.rvinit),.card:not(.rvinit)").forEach((el,i)=>{
    el.classList.add("rvinit"); el.style.transitionDelay=((i%5)*45)+"ms"; __rvObs.observe(el);
  });
}
initReveal();

function animateDashNums(){
  document.querySelectorAll("#dash .v").forEach(el=>{
    const txt=el.textContent.trim(); if(!txt||txt==="-"||el.dataset.counted===txt)return;
    const m=txt.match(/^([^0-9]*)([0-9][0-9,]*\.?[0-9]*)(.*)$/); if(!m)return;
    el.dataset.counted=txt;
    const target=parseFloat(m[2].replace(/,/g,"")); if(!isFinite(target)||target===0)return;
    const dec=(m[2].split(".")[1]||"").length, comma=m[2].includes(","), t0=performance.now();
    const fmt=v=>{let n=v.toFixed(dec); if(comma)n=Number(n).toLocaleString("en-US",{minimumFractionDigits:dec,maximumFractionDigits:dec}); return m[1]+n+m[3]};
    const step=t=>{const p=Math.min((t-t0)/650,1), e=1-Math.pow(1-p,3); el.textContent=fmt(target*e); if(p<1)requestAnimationFrame(step); else el.textContent=txt};
    requestAnimationFrame(step);
  });
}
setInterval(animateDashNums,700);

const CMDK_VIEWS=[["dash","01","Dashboard"],["cases","02","Use Cases"],["upload","03","Upload Center"],["run","04","Run Reconciliation"],["ledger","05","Ledger"],["forecast","06","Forecast and Collections"],["eval","07","Evaluations"],["health","08","Agent Health"],["method","09","Methodology"],["arch","10","Architecture"],["policy","11","Policy Studio"],["product","12","Product Thinking"]];
let cmdkSel=0, cmdkItems=[];
function cmdkAll(){
  const views=CMDK_VIEWS.map(v=>({grp:"Go to",num:v[1],label:v[2],run:()=>go(v[0])}));
  const acts=[
    {grp:"Actions",num:"RUN",label:"Load the demo case and run it live",run:()=>seedAndRun(undefined)},
    {grp:"Actions",num:"LIVE",label:"Run the active case live (streamed)",run:()=>{go("run"); setTimeout(()=>runLive($("live-btn")),350)}},
    {grp:"Actions",num:"APR",label:"Jump to the approvals queue",run:()=>{go("run"); scheduleApprovalsJump(250)}},
  ];
  return views.concat(acts);
}
function renderCmdk(q){
  const all=cmdkAll().filter(it=>!q||it.label.toLowerCase().includes(q.toLowerCase()));
  cmdkItems=all; cmdkSel=Math.min(cmdkSel,Math.max(all.length-1,0));
  let lastGrp="";
  $("cmdk-list").innerHTML=all.length?all.map((it,i)=>{
    const gh=it.grp!==lastGrp?`<div class="cg">${it.grp}</div>`:""; lastGrp=it.grp;
    return gh+`<div class="ci ${i===cmdkSel?"sel":""}" data-i="${i}"><span class="num">${it.num}</span>${esc(it.label)}</div>`;
  }).join(""):'<div class="ci">No match - try a view name</div>';
  $("cmdk-list").querySelectorAll(".ci[data-i]").forEach(el=>{
    el.onclick=()=>pickCmdk(Number(el.dataset.i));
    el.onmousemove=()=>{if(cmdkSel!==Number(el.dataset.i)){cmdkSel=Number(el.dataset.i); renderCmdk($("cmdk-in").value)}};
  });
}
function openCmdk(){ $("cmdk").classList.add("open"); cmdkSel=0; $("cmdk-in").value=""; renderCmdk(""); setTimeout(()=>$("cmdk-in").focus(),30); }
function closeCmdk(){ $("cmdk").classList.remove("open"); }
function pickCmdk(i){ const it=cmdkItems[i]; if(!it)return; closeCmdk(); it.run(); }
document.addEventListener("keydown",e=>{
  if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){ e.preventDefault(); $("cmdk").classList.contains("open")?closeCmdk():openCmdk(); return; }
  if(!$("cmdk").classList.contains("open"))return;
  if(e.key==="Escape")closeCmdk();
  else if(e.key==="ArrowDown"){e.preventDefault(); cmdkSel=Math.min(cmdkSel+1,cmdkItems.length-1); renderCmdk($("cmdk-in").value)}
  else if(e.key==="ArrowUp"){e.preventDefault(); cmdkSel=Math.max(cmdkSel-1,0); renderCmdk($("cmdk-in").value)}
  else if(e.key==="Enter"){e.preventDefault(); pickCmdk(cmdkSel)}
});
$("cmdk-in").addEventListener("input",e=>{cmdkSel=0; renderCmdk(e.target.value)});
$("cmdk").addEventListener("click",e=>{if(e.target.id==="cmdk")closeCmdk()});
/* ---- JD lens: the clean product look is the default; the lens restores
   the JD mapping banners for a hiring conversation. Persisted per browser. */
function toggleLens(){
  const off=document.body.classList.toggle("lens-off");
  localStorage.setItem("ac-lens", off?"off":"on");
  $("lens-btn").textContent="JD LENS: "+(off?"OFF":"ON");
}
if(localStorage.getItem("ac-lens")==="on"){ document.body.classList.remove("lens-off"); const lb=$("lens-btn"); if(lb)lb.textContent="JD LENS: ON"; }
/* ---- First-visit bootstrap: an empty workspace greets a first-time
   visitor with a wall of dashes. Instead, load the demo case and run it
   once, for real - every number shown afterwards is counted from that
   stored run. A deliberate Reset to empty is respected for the session. */
async function bootAuto(){
  try{
    if(sessionStorage.getItem("ac-empty")==="1") return;
    const ws=await refreshWorkspace(); if(!ws) return;
    if(ws.case||ws.latest_run||ws.open_invoices>0) return;
    await api("/api/v1/cases/seed/load",{method:"POST"});
    const ws2=await refreshWorkspace(); const pays=ws2?ws2.pending_payments:[];
    if(pays.length){ lastRun=await api("/api/v1/batches",{method:"POST",body:JSON.stringify({idempotency_key:"bootstrap-"+Date.now(),payments:pays})}); }
    await refreshWorkspace(); await refreshDash();
    // Settle pass: any dashboard read that was in flight from before the
    // batch has resolved by now, so one last refresh leaves every number
    // on the page describing the bootstrap run.
    setTimeout(async()=>{ await refreshWorkspace(); await refreshDash(); },1500);
    toast("Demo case loaded and run once - the numbers on this page are that run's real results. Reset to empty (case bar) starts clean.");
  }catch(e){}
}
refreshDash();
loadTenants();
bootAuto();
