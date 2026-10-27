/* Browser tests for docs/index.html.
   Run: serve the repo root, open /docs/index.html, then in the console
     await (await fetch("/tests/pwa.test.js?"+Date.now())).text().then(eval)
   and read window.__results. Every test leaves the app's storage as it found it. */
(async()=>{
const results=[]; const tick=()=>new Promise(r=>setTimeout(r,30));
async function test(name, fn){
  const snap={}; for(const k of Object.keys(localStorage)) snap[k]=localStorage.getItem(k);
  const cfg=JSON.stringify(CFG);
  try{ await fn(); results.push("PASS "+name); }
  catch(e){ results.push("FAIL "+name+" — "+e.message); }
  finally{
    localStorage.clear(); for(const k in snap) localStorage.setItem(k,snap[k]);
    CFG=JSON.parse(cfg); closePrint&&closePrint();
  }
}
const eq=(a,b,msg)=>{ if(a!==b) throw new Error((msg||"")+" expected "+b+", got "+a); };
const ok=(c,msg)=>{ if(!c) throw new Error(msg||"assertion failed"); };

/* a week with nothing filled, no archive */
/* like the app's own "new week" button: a fresh week has nothing to undo */
function freshWeek(ws){ ws=ws||"2026-10-26"; S.weekStart=ws; S.days=emptyWeek(ws); S.dirty=false; S.undo=null; }
function seedArchive(arch){ localStorage.setItem("agenda_archive",JSON.stringify(arch)); }

/* ── 1. no page jumps ───────────────────────────────────────────────── */
await test("schedule: changing a cell keeps the table's scroll position", async()=>{
  localStorage.removeItem("agenda_archive");
  freshWeek(); S.screen="sched"; render(); await tick();
  const wrap=document.querySelector(".tbl-wrap");
  wrap.scrollTop=wrap.scrollHeight; await tick();
  const before=wrap.scrollTop; ok(before>50,"table did not scroll in the test setup");
  const sel=document.querySelector('table.sched select[data-f="emb_pe"]');
  sel.value=sel.options[1].value; sel.dispatchEvent(new Event("change"));
  await tick();
  const after=document.querySelector(".tbl-wrap");
  /* the restored value must be what it was, give or take a pixel */
  ok(Math.abs(after.scrollTop-before)<=1, "table scrollTop "+after.scrollTop+" vs "+before);
});
await test("settings: tapping 🗑 on a row keeps the page where it was", async()=>{
  S.screen="settings"; render(); reopen("labels"); await tick();
  const del=document.querySelector("[data-delrow]");
  del.scrollIntoView({block:"center"}); await tick();
  const y=window.scrollY; ok(y>100,"page did not scroll in the test setup");
  del.click(); await tick();
  ok(Math.abs(window.scrollY-y)<=2, "window scrollY "+window.scrollY+" vs "+y);
  ok(document.querySelector('[data-delrow-yes]'),"confirm button missing");
  S.pendingConfirm=null;
});
await test("settings: 🗑 stays under the finger when sections above it are open", async()=>{
  S.screen="settings"; render();
  document.querySelectorAll("details.sect").forEach(d=>d.open=true);   // everything open by hand
  await tick();
  const dels=document.querySelectorAll("[data-delrow]"), del=dels[dels.length-1];
  del.scrollIntoView({block:"center"}); await tick();
  const key=del.dataset.delrow, top=del.getBoundingClientRect().top;
  del.click(); await tick();
  const again=document.querySelector(`[data-delrow="${key}"]`)||document.querySelector(`[data-delrow-yes="${key}"]`);
  ok(again,"row vanished");
  const top2=again.getBoundingClientRect().top;
  ok(Math.abs(top2-top)<=60, "button moved from "+Math.round(top)+" to "+Math.round(top2));
  S.pendingConfirm=null;
});
await test("settings: an open section stays open after another one re-renders", async()=>{
  S.screen="settings"; render();
  const d=document.querySelector('details.sect[data-sect="options"]'); d.open=true;
  render(); await tick();
  ok(document.querySelector('details.sect[data-sect="options"]').open,"options section closed");
});

/* ── 2. a real PDF file, for devices whose print dialog cannot save one ── */
await test("print: the PDF button builds an A4 PDF of the week", async()=>{
  freshWeek(); S.days[Object.keys(S.days)[0]].emb_pe="BUHO";
  S.screen="sched"; render(); doPrint(); await tick();
  ok(document.getElementById("printPdf"),"no PDF button in the print view");
  const blob=await buildSchedulePdf();
  ok(blob instanceof Blob && blob.size>5000,"no PDF blob");
  const head=await blob.slice(0,5).text(); eq(head,"%PDF-","file header");
  const txt=await blob.text();
  ok(/\/MediaBox \[0 0 595\.2\d* 841\.8\d*\]/.test(txt)||/\/MediaBox \[0 0 841\.8\d* 595\.2\d*\]/.test(txt),"page is not A4");
  window.__lastPdf=blob;
});

/* Safari lets a page open the share sheet only straight out of a tap. The PDF
   is therefore prepared while the print view is open, and the tap hands it
   over at once — no waiting in between. */
function stubShare(impl){
  const had={share:navigator.share, canShare:navigator.canShare};
  Object.defineProperty(navigator,"canShare",{value:()=>true,configurable:true});
  Object.defineProperty(navigator,"share",{value:impl,configurable:true});
  return ()=>{ Object.defineProperty(navigator,"share",{value:had.share,configurable:true});
               Object.defineProperty(navigator,"canShare",{value:had.canShare,configurable:true}); };
}
await test("pdf: the print view prepares the PDF before it is tapped", async()=>{
  freshWeek(); S.screen="sched"; render(); doPrint();
  ok(window.pdfPrepared, "no preparation started");
  const blob=await pdfPrepared();
  ok(blob&&blob.size>5000,"nothing prepared");
  const b=document.getElementById("printPdf");
  ok(!b.disabled && b.textContent===t("pdf_save"),"button not ready: "+b.textContent);
});
await test("pdf: a tap on a ready PDF opens the share sheet at once", async()=>{
  freshWeek(); S.screen="sched"; render(); doPrint(); await pdfPrepared();
  let calledSync=false, shared=null;
  const undo=stubShare(d=>{ shared=d; return Promise.resolve(); });
  try{ const p=savePdf(); calledSync=!!shared; await p; } finally{ undo(); }
  ok(calledSync,"share was not called straight from the tap");
  ok(shared.files[0].type==="application/pdf","shared something else");
});
await test("pdf: when the share sheet is refused, the file downloads instead", async()=>{
  freshWeek(); S.screen="sched"; render(); doPrint(); await pdfPrepared();
  const undo=stubShare(()=>Promise.reject(Object.assign(new Error("x"),{name:"NotAllowedError"})));
  const orig=HTMLAnchorElement.prototype.click; let dl=null;
  HTMLAnchorElement.prototype.click=function(){ dl=this.download; };
  try{ await savePdf(); } finally{ undo(); HTMLAnchorElement.prototype.click=orig; }
  ok(dl&&/\.pdf$/.test(dl),"no download fallback");
});
await test("pdf: changing the page direction prepares a fresh PDF", async()=>{
  freshWeek(); S.screen="sched"; render();
  savePrintSettings({...printSettings(), orientation:"portrait", mode:"single"});
  doPrint(); await pdfPrepared();
  document.querySelector('input[name="pvOrient"][value="landscape"]').click();
  const txt=await (await pdfPrepared()).text();
  ok(/\/MediaBox \[0 0 841\.8\d* 595\.2\d*\]/.test(txt),"still portrait");
});

/* ── 5. employees balanced within the week ───────────────────────────── */
/* eight past weeks in which HALCON and CHCHORRO did R and BUHO barely did */
function skewedArchive(){
  const arch={}, d0=new Date("2026-08-31T12:00:00");
  for(let w=0;w<8;w++){
    const wk=new Date(d0.getTime()+w*7*864e5), days={};
    for(let i=0;i<5;i++){ const k=new Date(wk.getTime()+i*864e5).toISOString().slice(0,10);
      days[k]={apt_pe:i%2?"HALCON":"CHCHORRO", emb_pe:i%2?"CHCHORRO+BUHO":"HALCON+BUHO",
               emb_il:"LEON", apt_il:"TORO"}; }
    arch[wk.toISOString().slice(0,10)]=days;
  }
  return arch;
}
const PE=["HALCON","CHCHORRO","BUHO"];
function personCounts(rk){
  const c={}; PE.forEach(n=>c[n]=0);
  Object.values(S.days).forEach(day=>String(day[rk]||"").split("+").filter(Boolean)
    .forEach(n=>{ if(n in c) c[n]++; }));
  return c;
}
await test("balance: in one week R is shared 2/2/1 among the three PE workers", async()=>{
  seedArchive(skewedArchive());
  for(let run=0;run<25;run++){
    freshWeek(); autoAssign();
    const c=personCounts("apt_pe"), v=Object.values(c);
    ok(Math.max(...v)-Math.min(...v)<=1, "run "+run+": R "+JSON.stringify(c));
  }
});
await test("balance: EMB pairs are shared evenly too (each name counted on its own)", async()=>{
  seedArchive(skewedArchive());
  for(let run=0;run<25;run++){
    freshWeek(); autoAssign();
    const c=personCounts("emb_pe"), v=Object.values(c);
    ok(Math.max(...v)-Math.min(...v)<=1, "run "+run+": EMB "+JSON.stringify(c));
  }
});
await test("balance: the odd R day goes to whoever had fewer R lately (BUHO)", async()=>{
  seedArchive(skewedArchive());
  for(let run=0;run<15;run++){
    freshWeek(); autoAssign();
    const c=personCounts("apt_pe");
    eq(c.BUHO,2,"run "+run+" "+JSON.stringify(c)+": BUHO R count");
  }
});

/* ── 3. a share for each axis ─────────────────────────────────────────── */
function letters(rk){ return Object.values(S.days).map(d=>axisLetterOf(d[rk])).filter(Boolean); }
await test("axes: an axis at 0% is never used, one at 100% always", async()=>{
  localStorage.removeItem("agenda_archive");
  CFG.entry_axis_rules={}; CFG.exit_axis_rules={};
  CFG.axes.forEach(a=>a.pct=a.id==="C"?100:0);
  for(let run=0;run<5;run++){ freshWeek(); autoAssign();
    const L=letters("axis_morning").concat(letters("axis_noon"));
    ok(L.length>=10 && L.every(x=>x==="C"), "letters "+L.join(",")); }
});
await test("axes: the axis share and the entry-hour share work together", async()=>{
  localStorage.removeItem("agenda_archive");
  /* entry 10 may use B or C half and half; the axis shares say C never */
  CFG.axes.forEach(a=>a.pct={A:40,B:60,C:0,D:0}[a.id]);
  for(let run=0;run<5;run++){ freshWeek(); autoAssign();
    Object.values(S.days).forEach(d=>{
      if(d.entry==="10"||d.entry==="10-T") eq(axisLetterOf(d.axis_morning),"B","entry "+d.entry);
      ok(axisLetterOf(d.axis_morning)!=="C","C used in the morning");
    }); }
});
await test("axes: saved shares must add up to 100 (warning otherwise)", async()=>{
  CFG.axes.forEach(a=>a.pct=10); freshWeek();
  ok(validate().some(e=>e.msg.includes("%")&&e.lvl==="err"&&/A.*B|axis|ציר/.test(e.msg)),"no share warning");
});

/* ── 4. preferred axes on a special-taxi day ──────────────────────────── */
await test("taxi: a YELLOW morning gets the preferred morning axis, YELLOW noon the noon one", async()=>{
  localStorage.removeItem("agenda_archive");
  CFG.taxi_axes={morning:["D"], noon:["A"]};
  for(let run=0;run<10;run++){ freshWeek(); autoAssign();
    const VS=CFG.special_values.vehicle_special;
    Object.values(S.days).forEach(d=>{
      if(d.vehicle_morning===VS) eq(axisLetterOf(d.axis_morning),"D","morning axis on a taxi day");
      if(d.vehicle_noon===VS)    eq(axisLetterOf(d.axis_noon),"A","noon axis on a taxi day");
    });
    ok(!validate().some(e=>e.msg.includes(rowLabel("axis_morning"))||e.msg.includes(rowLabel("axis_noon"))),
       "an axis broke an entry/exit rule");
  }
});
await test("taxi: an entry hour typed by hand is kept, even if it forbids the preferred axis", async()=>{
  localStorage.removeItem("agenda_archive");
  CFG.taxi_axes={morning:["D"], noon:[]};
  freshWeek(); const k=Object.keys(S.days)[0];
  S.days[k].vehicle_morning=CFG.special_values.vehicle_special; S.days[k].entry="10";   // 10 allows B,C
  autoAssign();
  eq(S.days[k].entry,"10","manual entry");
  ok(["B","C"].includes(axisLetterOf(S.days[k].axis_morning)),"axis "+S.days[k].axis_morning);
});
await test("settings: axis shares and taxi preferences can be edited and saved", async()=>{
  S.screen="settings"; render(); reopen("axes"); await tick();
  const pa=document.querySelector('[data-axpct="A"]'); ok(pa,"no share field for axis A");
  document.querySelectorAll("[data-axpct]").forEach(i=>i.value={A:70,B:10,C:10,D:10}[i.dataset.axpct]);
  document.getElementById("saveAxes").click(); await tick();
  eq(axisById("A").pct,70,"saved share");
  const cb=document.querySelector('[data-taxiax="noon"][data-letter="B"]'); ok(cb,"no taxi checkbox");
  cb.click(); document.getElementById("saveTaxiAxes").click(); await tick();
  ok((CFG.taxi_axes.noon||[]).includes("B"),"taxi preference not saved");
});

/* ── 4b. percentages inside the taxi preference ───────────────────────── */
await test("taxi %: over twelve weeks the taxi mornings split about 75/25", async()=>{
  localStorage.removeItem("agenda_archive");
  CFG.taxi_axes={morning:["A","D"], noon:[]};
  CFG.taxi_axes_pcts={morning:{A:75,D:25}, noon:{}};
  const VS=CFG.special_values.vehicle_special; let A=0, D=0, other=0;
  let ws="2026-08-03";
  for(let w=0;w<12;w++){
    freshWeek(ws); autoAssign();
    Object.values(S.days).forEach(d=>{ if(d.vehicle_morning!==VS) return;
      const L=axisLetterOf(d.axis_morning); if(L==="A") A++; else if(L==="D") D++; else other++; });
    const a=loadArchive(); a[ws]=S.days; saveArchive(a);
    ws=addDays(ws,7);
  }
  eq(other,0,"taxi mornings off the ticked axes");
  const share=A/(A+D);
  ok(share>=0.62&&share<=0.88, "A share "+A+"/"+(A+D));
});
await test("taxi %: the settings take a percentage per ticked axis and refuse a wrong total", async()=>{
  S.screen="settings"; render(); reopen("axes"); await tick();
  const cb=L=>document.querySelector(`[data-taxiax="noon"][data-letter="${L}"]`);
  const pc=L=>document.querySelector(`[data-taxipct="noon"][data-letter="${L}"]`);
  ok(pc("A"),"no percentage field");
  ok(pc("A").disabled,"field open while the axis is not ticked");
  cb("A").click(); cb("B").click(); await tick();
  ok(!pc("A").disabled,"field still closed after ticking");
  eq(+pc("A").value+ +pc("B").value,100,"ticking does not split evenly");
  pc("A").value=60; pc("B").value=60; pc("A").dispatchEvent(new Event("input"));
  document.getElementById("saveTaxiAxes").click(); await tick();
  ok(!((CFG.taxi_axes_pcts||{}).noon||{}).A,"saved a total of 120%");
  pc("A").value=60; pc("B").value=40;
  document.getElementById("saveTaxiAxes").click(); await tick();
  eq(CFG.taxi_axes_pcts.noon.A,60,"A share"); eq(CFG.taxi_axes_pcts.noon.B,40,"B share");
});
await test("taxi %: an older setting with ticks but no percentages splits evenly", async()=>{
  CFG.taxi_axes={morning:["B","C"], noon:[]}; delete CFG.taxi_axes_pcts;
  const w=taxiAxisPcts("morning"); eq(w.B,50,"B"); eq(w.C,50,"C");
});

/* ── v47 · 4. balance summary under the table ─────────────────────────── */
await test("summary: each role lists how many times each person holds it this week", async()=>{
  localStorage.removeItem("agenda_archive");
  freshWeek(); const k=Object.keys(S.days);
  ["BUHO","BUHO","HALCON","CHCHORRO","CHCHORRO"].forEach((n,i)=>S.days[k[i]].apt_pe=n);
  S.days[k[0]].emb_pe="HALCON+CHCHORRO";
  S.screen="sched"; render(); await tick();
  const line=document.querySelector('#balSum [data-bal="apt_pe"]');
  ok(line,"no summary line for R PE");
  ok(/BUHO\s*2/.test(line.textContent)&&/HALCON\s*1/.test(line.textContent)&&/CHCHORRO\s*2/.test(line.textContent),
     "R PE line: "+line.textContent);
  const emb=document.querySelector('#balSum [data-bal="emb_pe"]').textContent;
  ok(/HALCON\s*1/.test(emb)&&/CHCHORRO\s*1/.test(emb),"a pair is counted per name: "+emb);
});
await test("summary: a gap above one marks the line", async()=>{
  freshWeek(); const k=Object.keys(S.days);
  k.forEach(d=>S.days[d].apt_pe="BUHO");                    // 5 / 0 / 0
  S.screen="sched"; render(); await tick();
  ok(document.querySelector('#balSum [data-bal="apt_pe"]').classList.contains("bal-off"),"not marked");
  k.forEach((d,i)=>S.days[d].apt_pe=PE[i%3]);               // 2 / 2 / 1
  render(); await tick();
  ok(!document.querySelector('#balSum [data-bal="apt_pe"]').classList.contains("bal-off"),"marked while balanced");
});
await test("summary: follows a change typed into a cell", async()=>{
  freshWeek(); S.screen="sched"; render(); await tick();
  const sel=document.querySelector('table.sched select[data-f="apt_il"]');
  sel.value="LEON"; sel.dispatchEvent(new Event("change")); await tick();
  ok(/LEON\s*1/.test(document.querySelector('#balSum [data-bal="apt_il"]').textContent),"summary did not update");
});

/* ── v47 · 5. undo auto-assign ───────────────────────────────────────── */
await test("undo: ↶ brings back the exact week from before ⚡", async()=>{
  freshWeek(); const k=Object.keys(S.days)[1];
  S.days[k].emb_il="TORO"; S.screen="sched"; render();
  const before=JSON.stringify(S.days);
  ok(!document.getElementById("btnUndo")||document.getElementById("btnUndo").disabled,"undo offered before ⚡");
  document.getElementById("btnAuto").click(); await tick();
  ok(JSON.stringify(S.days)!==before,"⚡ changed nothing");
  document.getElementById("btnUndo").click(); await tick();
  eq(JSON.stringify(S.days),before,"week after undo");
  ok(document.getElementById("btnUndo").disabled,"undo still offered after use");
});
await test("undo: saving the week ends the undo", async()=>{
  freshWeek(); S.screen="sched"; render();
  document.getElementById("btnAuto").click(); await tick();
  document.getElementById("btnSave").click(); await tick();
  ok(document.getElementById("btnUndo").disabled,"undo offered after save");
});

/* ── v47 · 9. values read left to right ──────────────────────────────── */
function charsInOrder(cell,a,b){
  const tn=[...cell.childNodes].find(n=>n.nodeType===3&&n.textContent.includes(a));
  const r=document.createRange(), x=ch=>{ const i=tn.textContent.indexOf(ch);
    r.setStart(tn,i); r.setEnd(tn,i+1); return r.getBoundingClientRect().left; };
  return x(a)<x(b);
}
await test("print: 13-D prints as 13-D, not D-13, in the Hebrew sheet", async()=>{
  freshWeek(); S.lang="he"; const k=Object.keys(S.days)[0];
  S.days[k].entry="13-D"; S.screen="sched"; render(); doPrint(); await tick();
  const td=[...document.querySelectorAll("#printArea td")].find(x=>x.textContent==="13-D");
  ok(td,"cell not found");
  ok(charsInOrder(td,"1","D"),"the 1 is not left of the D");
  /* a Hebrew value still reads right to left */
  S.days[k].theater="משקפת"; paintPrintArea(); await tick();
  const he=[...document.querySelectorAll("#printArea td")].find(x=>x.textContent==="משקפת");
  ok(!charsInOrder(he,"מ","ת"),"Hebrew value turned left to right");
});

await test("screen: a 13-D cell reads left to right, a Hebrew cell right to left", async()=>{
  freshWeek(); S.lang="he"; const k=Object.keys(S.days)[0];
  S.days[k].entry="13-D"; S.days[k].theater="משקפת"; S.screen="sched"; render(); await tick();
  const sel=f=>document.querySelector(`table.sched select[data-dk="${k}"][data-f="${f}"]`);
  eq(sel("entry").dir,"ltr","13-D cell direction");
  eq(sel("theater").dir,"rtl","Hebrew cell direction");
  /* the choice follows the value as it changes */
  sel("entry").value="10"; sel("entry").dispatchEvent(new Event("change")); await tick();
  eq(sel("entry").dir,"ltr","10 cell direction");
});

window.__results=results;
return results;
})();
