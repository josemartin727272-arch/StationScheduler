/* Browser tests for docs/index.html.
   Run: serve the repo root, open /docs/index.html, then in the console
     const sc=document.createElement("script"); sc.src="/tests/pwa.test.js?"+Date.now();
     document.head.appendChild(sc);
   and read window.__results once it is set. (Loaded as a script, not eval'ed:
   the page's Content-Security-Policy forbids eval, as it should.)
   Every test leaves the app's storage as it found it. */
window.__results=null;
(async()=>{
const results=[]; const tick=()=>new Promise(r=>setTimeout(r,30));
const __origCfg=JSON.stringify(CFG);
CFG.groups[0].employees=["LEON","TORO"]; CFG.groups[0].active=true; CFG.groups[0].lang="he";
CFG.groups[1].employees=["HALCON","CHCHORRO","BUHO"]; CFG.groups[1].active=true; CFG.groups[1].lang="es";
CFG.vacation_budget={LEON:14,TORO:14,HALCON:30,CHCHORRO:30,BUHO:30};
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

/* ── v48 · 6. fixed weekday assignments ──────────────────────────────── */
const MON="2026-10-26", TUE="2026-10-27", WED="2026-10-28";
function newWeekByButton(ws){
  S.screen="sched"; S.days=null; S.undo=null; localStorage.removeItem("agenda_draft");
  render(); document.getElementById("weekPick").value=ws;
  document.getElementById("weekPick").dispatchEvent(new Event("change"));
  document.getElementById("btnGen").click();
}
await test("fixed: a rule added in Settings is saved", async()=>{
  CFG.fixed_rules=[]; S.screen="settings"; render(); reopen("fixed"); await tick();
  const f=id=>document.getElementById(id);
  ok(f("fxDay")&&f("fxRow")&&f("fxVal"),"no fixed-rule form");
  f("fxDay").value="monday"; f("fxRow").value="emb_il"; f("fxRow").dispatchEvent(new Event("change"));
  await tick(); f("fxVal").value="TORO"; f("fxAdd").click(); await tick();
  eq(JSON.stringify(CFG.fixed_rules),JSON.stringify([{day:"monday",row:"emb_il",value:"TORO"}]),"saved rule");
});
await test("fixed: a new week opens with the fixed cell filled, and ⚡ keeps it", async()=>{
  localStorage.removeItem("agenda_archive"); CFG.away_calendar=[];
  CFG.fixed_rules=[{day:"monday",row:"emb_il",value:"TORO"}];
  newWeekByButton(MON); await tick();
  eq(S.days[MON].emb_il,"TORO","Monday EMB IL");
  eq(S.days[TUE].emb_il,"","Tuesday untouched");
  document.getElementById("btnAuto").click(); await tick();
  eq(S.days[MON].emb_il,"TORO","after ⚡");
});
await test("fixed: 🗑 Clear puts the fixed cell back", async()=>{
  CFG.fixed_rules=[{day:"monday",row:"emb_il",value:"TORO"}]; CFG.away_calendar=[];
  newWeekByButton(MON); await tick();
  document.getElementById("btnAuto").click(); await tick();
  document.getElementById("btnClear").click(); await tick();
  document.getElementById("clearYes").click(); await tick();
  eq(S.days[MON].emb_il,"TORO","after clear");
  eq(S.days[TUE].apt_il,"","clear emptied the rest");
});

/* ── v48 · 8. vacation calendar ──────────────────────────────────────── */
await test("calendar: a vacation entered ahead lands in its week and keeps the person free", async()=>{
  localStorage.removeItem("agenda_archive"); CFG.fixed_rules=[];
  CFG.away_calendar=[{name:"BUHO", kind:"vacation", from:TUE, to:WED}];
  newWeekByButton(MON); await tick();
  ok(awayList(S.days[TUE],"vacation").includes("BUHO"),"Tuesday");
  ok(awayList(S.days[WED],"vacation").includes("BUHO"),"Wednesday");
  ok(!awayList(S.days[MON],"vacation").includes("BUHO"),"Monday");
  document.getElementById("btnAuto").click(); await tick();
  [TUE,WED].forEach(d=>secRows().forEach(rk=>ok(!String(S.days[d][rk]).includes("BUHO"),"BUHO placed on "+d)));
});
function secRows(){ return allSections().map(x=>x.sec.row_key); }
await test("calendar: a vacation entered after the week was saved shows when it is opened, manual marks kept", async()=>{
  CFG.fixed_rules=[]; CFG.away_calendar=[];
  freshWeek(MON); S.days[MON].trip=["LEON"];
  const a={}; a[MON]=JSON.parse(JSON.stringify(S.days)); saveArchive(a);
  CFG.away_calendar=[{name:"TORO", kind:"trip", from:MON, to:MON}];
  S.screen="archive"; render(); await tick();
  document.querySelector(`[data-load="${MON}"]`).click(); await tick();
  const trip=awayList(S.days[MON],"trip");
  ok(trip.includes("TORO")&&trip.includes("LEON"),"trip list "+JSON.stringify(trip));
});
await test("calendar: entries are added in Settings; an end before the start is refused", async()=>{
  CFG.away_calendar=[]; S.screen="settings"; render(); reopen("calendar"); await tick();
  const f=id=>document.getElementById(id);
  ok(f("calName")&&f("calKind")&&f("calFrom")&&f("calTo"),"no calendar form");
  f("calName").value="HALCON"; f("calKind").value="vacation"; f("calFrom").value="2026-11-10"; f("calTo").value="2026-11-03";
  f("calAdd").click(); await tick();
  eq(CFG.away_calendar.length,0,"saved a backwards range");
  f("calFrom").value="2026-11-03"; f("calTo").value="2026-11-10"; f("calAdd").click(); await tick();
  eq(JSON.stringify(CFG.away_calendar),JSON.stringify([{name:"HALCON",kind:"vacation",from:"2026-11-03",to:"2026-11-10"}]),"saved entry");
});
await test("fixed vs calendar: someone away is not placed by a fixed rule, and a warning says why", async()=>{
  localStorage.removeItem("agenda_archive");
  CFG.fixed_rules=[{day:"monday",row:"emb_il",value:"TORO"}];
  CFG.away_calendar=[{name:"TORO", kind:"vacation", from:MON, to:MON}];
  newWeekByButton(MON); await tick();
  eq(S.days[MON].emb_il,"","TORO placed while on vacation");
  ok(validate().some(e=>e.msg.includes("TORO")&&e.msg.includes("📌")),"no warning about the fixed rule");
});
await test("old settings without rules or calendar still load", async()=>{
  const raw=JSON.parse(JSON.stringify(CFG)); delete raw.fixed_rules; delete raw.away_calendar;
  localStorage.setItem("agenda_config",JSON.stringify(raw));
  const c=loadConfig();
  ok(Array.isArray(c.fixed_rules)&&c.fixed_rules.length===0,"fixed_rules");
  ok(Array.isArray(c.away_calendar)&&c.away_calendar.length===0,"away_calendar");
});

/* ── v48 · 7. why this value ─────────────────────────────────────────── */
await test("why: with 💬 on, an auto-filled role says why it went to that person", async()=>{
  localStorage.removeItem("agenda_archive"); CFG.fixed_rules=[]; CFG.away_calendar=[];
  newWeekByButton(MON); await tick();
  document.getElementById("btnAuto").click(); await tick();
  S.showWhy=false; render(); await tick();       // a fresh page starts with 💬 off
  ok(!document.querySelector("table.sched .why"),"reasons shown before asking");
  document.getElementById("btnWhy").click(); await tick();
  const cell=document.querySelector(`table.sched select[data-dk="${WED}"][data-f="apt_pe"]`).closest("td");
  const why=cell.querySelector(".why");
  ok(why&&why.textContent.trim().length>3,"no reason under R PE");
  ok(why.textContent.includes(t("why_week_word")),"reason does not speak of the week: "+why.textContent);
});
await test("why: a taxi-day axis names the taxi split", async()=>{
  localStorage.removeItem("agenda_archive");
  CFG.taxi_axes={morning:["D"],noon:[]}; CFG.taxi_axes_pcts={morning:{D:100},noon:{}};
  newWeekByButton(MON); await tick();
  document.getElementById("btnAuto").click(); await tick();
  const VS=CFG.special_values.vehicle_special;
  const dk=Object.keys(S.days).find(d=>S.days[d].vehicle_morning===VS);
  ok(dk,"no taxi morning this week");
  ok(String(S.why[dk+"|axis_morning"]||"").includes("100%"),"axis reason: "+S.why[dk+"|axis_morning"]);
});
await test("why: changing a cell by hand drops its reason", async()=>{
  localStorage.removeItem("agenda_archive");
  newWeekByButton(MON); await tick();
  document.getElementById("btnAuto").click(); await tick();
  ok(S.why[MON+"|apt_il"],"no reason to begin with");
  const sel=document.querySelector(`table.sched select[data-dk="${MON}"][data-f="apt_il"]`);
  sel.value=""; sel.dispatchEvent(new Event("change")); await tick();
  ok(!S.why[MON+"|apt_il"],"reason kept after a manual change");
});

/* ── v49 · 10. a personal WhatsApp message per worker ────────────────── */
function weekForMessages(){
  localStorage.removeItem("agenda_archive"); CFG.fixed_rules=[]; CFG.away_calendar=[];
  freshWeek(MON);
  S.days[MON].emb_pe="HALCON+BUHO"; S.days[MON].work_hours="7:30-16:00";
  S.days[TUE].apt_pe="BUHO";
  S.days[WED].vacation=["BUHO"];
  S.days[MON].emb_il="TORO";
}
await test("message: a PE worker gets his own week in Spanish", async()=>{
  weekForMessages();
  const m=workerMessage("BUHO");
  ok(/lunes/i.test(m)&&/martes/i.test(m),"Spanish day names missing:\n"+m);
  ok(/EMB/.test(m)&&/\bR\b/.test(m),"roles missing:\n"+m);
  ok(m.includes("7:30-16:00"),"hours missing:\n"+m);
  ok(m.includes(I18N.es.cal_vac),"vacation day missing:\n"+m);
  ok(!m.includes("TORO"),"someone else's place in it:\n"+m);
});
await test("message: an IL worker gets Hebrew", async()=>{
  weekForMessages();
  ok(workerMessage("TORO").includes(I18N.he.dow_monday),"no Hebrew Monday");
});
await test("message: the language follows the group setting", async()=>{
  weekForMessages(); groupById("g2").lang="en";
  ok(/Monday/.test(workerMessage("BUHO")),"group language ignored");
});
await test("message: older settings give IL Hebrew and PE Spanish", async()=>{
  const raw=JSON.parse(JSON.stringify(CFG)); raw.groups.forEach(g=>delete g.lang);
  localStorage.setItem("agenda_config",JSON.stringify(raw));
  const c=loadConfig();
  eq(c.groups[0].lang,"he","IL"); eq(c.groups[1].lang,"es","PE");
});
await test("message: Settings choose a language per group", async()=>{
  S.screen="settings"; render(); reopen("groups"); await tick();
  const sel=document.querySelector('[data-glang="g2"]'); ok(sel,"no language picker");
  sel.value="en"; document.getElementById("saveGroups").click(); await tick();
  eq(groupById("g2").lang,"en","saved language");
});
await test("send: the panel lists every worker and a tap opens the share sheet at once", async()=>{
  weekForMessages(); S.screen="sched"; S.sendOpen=false; render();
  document.getElementById("btnSend").click(); await tick();
  const rows=[...document.querySelectorAll("[data-send]")].map(b=>b.dataset.send);
  eq(rows.sort().join(","),allEmps().slice().sort().join(","),"workers listed");
  let shared=null;
  const undo=stubShare(d=>{ shared=d; return Promise.resolve(); });
  try{ document.querySelector('[data-send="BUHO"]').click(); } finally{ undo(); }
  ok(shared&&shared.text===workerMessage("BUHO"),"share not called straight from the tap");
  await tick();
  ok(document.querySelector('[data-send="BUHO"]').closest("[data-sent]"),"not marked as sent");
});
await test("send: without a share sheet, WhatsApp opens with the text", async()=>{
  weekForMessages(); S.screen="sched"; S.sendOpen=false; render();
  document.getElementById("btnSend").click(); await tick();
  const had=navigator.share, hadOpen=window.open; let url=null;
  Object.defineProperty(navigator,"share",{value:undefined,configurable:true});
  window.open=u=>{ url=u; return null; };
  try{ document.querySelector('[data-send="TORO"]').click(); }
  finally{ Object.defineProperty(navigator,"share",{value:had,configurable:true}); window.open=hadOpen; }
  ok(url&&url.startsWith("https://wa.me/?text=")&&decodeURIComponent(url.slice(20))===workerMessage("TORO"),"url "+url);
});

/* ── v50 · 12. renaming an employee keeps their history ──────────────── */
function renameSetup(){
  const arch={}; arch[MON]={}; arch[MON][MON]={apt_pe:"BUHO", emb_pe:"HALCON+BUHO", vacation:[], trip:["BUHO"], other_empl:"BUHO"};
  arch[MON][TUE]={apt_pe:"HALCON", emb_pe:"CHCHORRO+BUHO", vacation:["BUHO"], trip:[]};
  seedArchive(arch);
  CFG.vacation_budget.BUHO=21;
  CFG.fixed_rules=[{day:"monday",row:"emb_pe",value:"HALCON+BUHO"}];
  CFG.away_calendar=[{name:"BUHO",kind:"trip",from:"2026-12-01",to:"2026-12-03"}];
  freshWeek(MON); S.days[MON].apt_pe="BUHO";
  S.screen="settings"; render(); reopen("groups");
}
async function renameByUi(from,to){
  const f=id=>document.getElementById(id);
  f("rnFrom").value=from; f("rnTo").value=to; f("rnGo").click(); await tick();
  const yes=f("rnYes"); if(yes){ yes.click(); await tick(); }
}
await test("rename: asks first, and changes nothing until confirmed", async()=>{
  renameSetup(); await tick();
  const f=id=>document.getElementById(id);
  ok(f("rnFrom")&&f("rnTo")&&f("rnGo"),"no rename form");
  f("rnFrom").value="BUHO"; f("rnTo").value="PUMA"; f("rnGo").click(); await tick();
  ok(f("rnYes"),"no confirmation");
  ok(allEmps().includes("BUHO"),"renamed before confirming");
});
await test("rename: every place the name lives follows it", async()=>{
  renameSetup(); await tick(); await renameByUi("BUHO","PUMA");
  ok(allEmps().includes("PUMA")&&!allEmps().includes("BUHO"),"groups");
  eq(CFG.vacation_budget.PUMA,21,"budget moved"); ok(!("BUHO" in CFG.vacation_budget),"old budget key left");
  eq(CFG.fixed_rules[0].value,"HALCON+PUMA","fixed rule");
  eq(CFG.away_calendar[0].name,"PUMA","calendar");
  const a=loadArchive()[MON];
  eq(a[MON].apt_pe,"PUMA","archive single"); eq(a[MON].emb_pe,"HALCON+PUMA","archive pair");
  eq(JSON.stringify(a[MON].trip),'["PUMA"]',"archive trip"); eq(a[MON].other_empl,"PUMA","archive other task");
  eq(JSON.stringify(a[TUE].vacation),'["PUMA"]',"archive vacation");
  eq(S.days[MON].apt_pe,"PUMA","open week");
  ok(!JSON.stringify(loadArchive()).includes("BUHO"),"BUHO left somewhere in the archive");
});
await test("rename: a taken, empty or '+' name is refused", async()=>{
  for(const bad of ["HALCON","","A+B","A,B"]){
    renameSetup(); await tick(); await renameByUi("BUHO",bad);
    ok(allEmps().includes("BUHO"),"accepted '"+bad+"'");
  }
});
await test("rename: statistics then show one person, not two", async()=>{
  renameSetup(); await tick(); await renameByUi("BUHO","PUMA");
  S.screen="stats"; S.statsTab="year"; S.statsYear="2026"; render(); await tick();
  const tx=document.getElementById("app").textContent;
  ok(tx.includes("PUMA")&&!tx.includes("BUHO"),"stats still split the person");
});

/* ── v51 · privacy and hardening ──────────────────────────────────────── */
const REAL=["LEON","TORO","HALCON","CHCHORRO","BUHO"];
await test("privacy: the page asks search engines not to list it", async()=>{
  const m=document.querySelector('meta[name="robots"]');
  ok(m&&/noindex/.test(m.content)&&/nofollow/.test(m.content),"no noindex/nofollow");
});
await test("privacy: the published code holds none of the station's real names", async()=>{
  const src=await (await fetch("/docs/index.html?"+Date.now())).text();
  const found=REAL.filter(n=>src.includes(n));
  eq(found.join(","),"","names in index.html");
});
await test("privacy: a station's own saved names and budgets survive the generic defaults", async()=>{
  const raw=JSON.parse(JSON.stringify(CFG));          // the fixture: real names, real budgets
  localStorage.setItem("agenda_config",JSON.stringify(raw));
  const c=loadConfig();
  eq(c.groups[1].employees.join(","),"HALCON,CHCHORRO,BUHO","employees");
  eq(JSON.stringify(c.vacation_budget),JSON.stringify(raw.vacation_budget),"budget gained default keys");
});
await test("hardening: a policy forbids sending anything to another site", async()=>{
  const m=document.querySelector('meta[http-equiv="Content-Security-Policy"]');
  ok(m,"no Content-Security-Policy");
  const seen=[]; const on=e=>seen.push(e.violatedDirective+" "+e.blockedURI);
  document.addEventListener("securitypolicyviolation",on);
  try{
    await fetch("https://example.com/leak?x=1").catch(()=>{});
    const img=new Image(); img.src="https://example.com/leak.png?x=1";
    await new Promise(r=>setTimeout(r,300));
  } finally{ document.removeEventListener("securitypolicyviolation",on); }
  ok(seen.some(x=>x.startsWith("connect-src")&&x.includes("example.com")),"fetch not blocked: "+seen.join(" | "));
  ok(seen.some(x=>x.startsWith("img-src")&&x.includes("example.com")),"image not blocked: "+seen.join(" | "));
});
await test("hardening: the PDF still builds under the policy", async()=>{
  freshWeek(); S.screen="sched"; render(); doPrint();
  const b=await buildSchedulePdf(); closePrint();
  ok(b&&b.size>5000,"no PDF");
});

/* ── v52 · password screen ─────────────────────────────────────────────── */
await test("lock: a code made from a password checks that password and no other", async()=>{
  const code=await makeLockCode("taxi-Secret 2026");
  ok(/^v1:[0-9a-f]{32}:\d+:[0-9a-f]{64}$/.test(code),"code shape: "+code);
  ok(!code.includes("Secret"),"the password is inside the code");
  ok(await checkPassword("taxi-Secret 2026",code),"right password refused");
  ok(!(await checkPassword("taxi-secret 2026",code)),"wrong password accepted");
});
await test("lock: with a site lock the app stays hidden until the password is given", async()=>{
  const code=await makeLockCode("abcd1234");
  localStorage.removeItem("agenda_unlock");
  document.getElementById("app").innerHTML="";
  startApp(code); await tick();
  const ls=document.getElementById("lockScreen");
  /* fixed-position: offsetParent is always null, so measure it instead */
  ok(ls&&ls.getBoundingClientRect().width>200&&getComputedStyle(ls).display!=="none","no lock screen");
  eq(document.getElementById("app").innerHTML,"","app drawn behind the lock");
  document.getElementById("lockPw").value="wrong-one"; document.getElementById("lockGo").click();
  await new Promise(r=>setTimeout(r,1500));
  ok(document.getElementById("lockScreen"),"wrong password let in");
  ok(document.getElementById("lockErr").textContent.length>0,"no error shown");
  document.getElementById("lockPw").value="abcd1234"; document.getElementById("lockRemember").checked=true;
  document.getElementById("lockGo").click();
  await new Promise(r=>setTimeout(r,1500));
  ok(!document.getElementById("lockScreen"),"right password kept out");
  ok(document.getElementById("app").innerHTML.length>0,"app not drawn after unlock");
  ok(!Object.values(localStorage).some(v=>String(v).includes("abcd1234")),"password stored in plain text");
  /* remembered: the next open goes straight in */
  document.getElementById("app").innerHTML=""; startApp(code); await tick();
  ok(!document.getElementById("lockScreen"),"asked again on a remembered device");
});
await test("lock: without 'remember' the next open asks again", async()=>{
  const code=await makeLockCode("abcd1234");
  localStorage.removeItem("agenda_unlock");
  startApp(code); await tick();
  document.getElementById("lockPw").value="abcd1234"; document.getElementById("lockRemember").checked=false;
  document.getElementById("lockGo").click(); await new Promise(r=>setTimeout(r,1500));
  startApp(code); await tick();
  ok(document.getElementById("lockScreen"),"remembered without being asked to");
  document.getElementById("lockScreen").remove();
});
await test("lock: no site lock means the app opens as before", async()=>{
  document.getElementById("app").innerHTML=""; startApp(null); await tick();
  ok(!document.getElementById("lockScreen"),"lock shown with no lock set");
  ok(document.getElementById("app").innerHTML.length>0,"app not drawn");
});
await test("lock: Settings turn a password into a code to send, refusing short or mismatched ones", async()=>{
  S.screen="settings"; render(); reopen("lock"); await tick();
  const f=id=>document.getElementById(id);
  ok(f("lkPw")&&f("lkPw2")&&f("lkMake"),"no password form");
  f("lkPw").value="short"; f("lkPw2").value="short"; f("lkMake").click(); await new Promise(r=>setTimeout(r,800));
  ok(!f("lkCode")||!f("lkCode").value,"made a code for a short password");
  f("lkPw").value="abcdefgh9"; f("lkPw2").value="abcdefgh8"; f("lkMake").click(); await new Promise(r=>setTimeout(r,800));
  ok(!f("lkCode")||!f("lkCode").value,"made a code for mismatched passwords");
  f("lkPw").value="abcdefgh9"; f("lkPw2").value="abcdefgh9"; f("lkMake").click(); await new Promise(r=>setTimeout(r,1500));
  const code=f("lkCode")&&f("lkCode").value;
  ok(code&&await checkPassword("abcdefgh9",code),"code does not match the password");
  eq(f("lkPw").value,"","password left in the field");
});

/* ── v54 · the guide, end to end ──────────────────────────────────────── */
await test("guide: every chapter renders in all three languages, quick start open", async()=>{
  const ids=["intro","start","screens","setup","build","print","vacation","archive","stats","install","faq","tips","news"];
  for(const lg of ["he","en","es"]){
    S.lang=lg; S.screen="guide"; render(); await tick();
    const ch=[...document.querySelectorAll("details.guide-ch")];
    eq(ch.map(d=>d.dataset.guide).join(","),ids.join(","),lg+" chapters");
    ch.forEach(d=>ok(d.querySelector(".guide-body").textContent.trim().length>60,lg+" "+d.dataset.guide+" empty"));
    ok(document.querySelector('details.guide-ch[data-guide="start"]').open,lg+" quick start closed");
  }
  S.lang="he";
});
await test("guide: it covers every feature a new worker meets", async()=>{
  S.lang="he"; S.screen="guide"; render(); await tick();
  const tx=document.getElementById("app").textContent;
  ["🔒","📌","🏖","💬","↶","⚖️","📲","📄","✏️","% שימוש בציר","מונית מיוחדת","לוח חופשות","שפת ההודעות","גיבוי"]
    .forEach(w=>ok(tx.includes(w),"guide misses "+w));
  ok(!tx.includes("בהגדרות ← 🖨️ הגדרות הדפסה"),"stale text: print settings in Settings");
});

/* ── v55 · Hebrew option values follow the display language ──────────── */
function theaterWeek(){
  localStorage.removeItem("agenda_archive"); CFG.fixed_rules=[]; CFG.away_calendar=[];
  freshWeek(MON); S.days[MON].theater="משקפת"; S.days[TUE].theater="רדיו"; S.days[WED].work_hours="חג";
}
await test("values: the theater cell shows the display language, the data stays Hebrew", async()=>{
  theaterWeek();
  for(const [lg,want] of [["en","Binoculars"],["es","Prismáticos"],["he","משקפת"]]){
    S.lang=lg; S.screen="sched"; render(); await tick();
    const sel=document.querySelector(`table.sched select[data-dk="${MON}"][data-f="theater"]`);
    eq(sel.options[sel.selectedIndex].textContent,want,lg+" label");
    eq(sel.value,"משקפת",lg+" stored value");
  }
  S.lang="en"; render(); await tick();
  const sel=document.querySelector(`table.sched select[data-dk="${TUE}"][data-f="theater"]`);
  const pic=[...sel.options].find(o=>o.textContent==="Photos"); ok(pic,"no Photos option");
  sel.value=pic.value; sel.dispatchEvent(new Event("change")); await tick();
  eq(S.days[TUE].theater,"תמונות","choosing in English stored something else");
  S.lang="he";
});
await test("values: holiday in the hours row reads Holiday / Feriado", async()=>{
  theaterWeek(); S.lang="es"; S.screen="sched"; render(); await tick();
  const sel=document.querySelector(`table.sched select[data-dk="${WED}"][data-f="work_hours"]`);
  eq(sel.options[sel.selectedIndex].textContent,"Feriado","Spanish holiday");
  S.lang="he";
});
await test("values: print, Excel and statistics use the display language too", async()=>{
  theaterWeek(); S.lang="en"; S.screen="sched"; render(); doPrint(); await tick();
  ok([...document.querySelectorAll("#printArea td")].some(td=>td.textContent==="Binoculars"),"print shows Hebrew");
  closePrint();
  const csv=scheduleCsv(S.days); ok(csv.includes("Binoculars")&&!csv.includes("משקפת"),"Excel shows Hebrew");
  const a={}; a[MON]=S.days; saveArchive(a);
  S.screen="stats"; S.statsTab="week"; render(); await tick();
  const tx=document.getElementById("app").textContent;
  ok(tx.includes("Binoculars")&&!tx.includes("משקפת"),"statistics show Hebrew");
  S.lang="he";
});
await test("values: a worker's message is in their language", async()=>{
  theaterWeek();
  CFG.value_labels={...(CFG.value_labels||{}), "בוקר":{en:"Morning",es:"Mañana"}};
  S.days[TUE].work_hours="בוקר"; S.days[TUE].apt_pe="BUHO";
  const m=workerMessage("BUHO");
  ok(m.includes("Mañana")&&!m.includes("בוקר"),"hours not translated:\n"+m);
});
await test("values: Settings let you edit the English and Spanish of each Hebrew value", async()=>{
  S.lang="he"; S.screen="settings"; render(); reopen("vlabels"); await tick();
  const en=document.querySelector('[data-vlab="משקפת"][data-lang="en"]');
  ok(en,"no translation field for משקפת");
  en.value="Field glasses"; document.getElementById("saveVLabels").click(); await tick();
  eq(CFG.value_labels["משקפת"].en,"Field glasses","saved translation");
  S.lang="en"; eq(valueLabel("משקפת"),"Field glasses","label after edit"); S.lang="he";
});
await test("values: older settings get the shipped translations", async()=>{
  const raw=JSON.parse(JSON.stringify(CFG)); delete raw.value_labels;
  localStorage.setItem("agenda_config",JSON.stringify(raw));
  const c=loadConfig();
  eq(((c.value_labels||{})["רדיו"]||{}).es,"Radio","Spanish radio");
});

/* ── v56 · printing fills the page ─────────────────────────────────────── */
const inside=(c,b)=>c.x>=-0.01&&c.y>=-0.01&&c.x+c.w<=b.w+0.01&&c.y+c.h<=b.h+0.01;
const area=cs=>cs.reduce((a,c)=>a+c.w*c.h,0);
await test("layout: 4 copies use most of the page, all inside it", async()=>{
  freshWeek(); S.screen="sched"; render();
  const L=pageLayout({mode:"multi",by:"count",copies:4,orientation:"portrait",w:9,h:6});
  eq(L.cells.length,4,"cells"); L.cells.forEach(c=>ok(inside(c,L.box),"cell off the page"));
  ok(area(L.cells)/(L.box.w*L.box.h)>=0.9,"copies cover "+Math.round(area(L.cells)/(L.box.w*L.box.h)*100)+"%");
});
await test("layout: 5 copies stay on one page", async()=>{
  const L=pageLayout({mode:"multi",by:"count",copies:5,orientation:"portrait",w:9,h:6});
  eq(L.cells.length,5,"cells"); L.cells.forEach(c=>ok(inside(c,L.box),"cell off the page"));
});
await test("layout: by size, the page is tiled with as many copies as fit", async()=>{
  const L=pageLayout({mode:"multi",by:"size",copies:4,orientation:"portrait",w:9,h:6});
  eq(L.cols+"x"+L.rows,"2x4","grid for 9x6 cm on portrait A4");
  eq(L.cells.length,8,"copies");
  L.cells.forEach(c=>{ ok(inside(c,L.box),"cell off the page"); ok(Math.abs(c.w-90)<0.01&&Math.abs(c.h-60)<0.01,"cell size "+c.w+"x"+c.h); });
  const big=pageLayout({mode:"multi",by:"size",copies:4,orientation:"portrait",w:30,h:40});
  eq(big.cells.length,1,"oversize copy"); ok(inside(big.cells[0],big.box),"oversize copy off the page");
});
async function printWith(ps){
  freshWeek(); S.screen="sched"; render(); autoAssign();
  savePrintSettings({...printSettings(),...ps}); doPrint(); await pdfPrepared();
}
const MMPX=96/25.4;
await test("fill: each copy's table fills its frame, top to bottom", async()=>{
  await printWith({mode:"multi",by:"count",copies:4,orientation:"portrait"});
  const copies=[...document.querySelectorAll("#printArea .pcopy")]; eq(copies.length,4,"copies drawn");
  copies.forEach(c=>{ const cb=c.getBoundingClientRect(), tb=c.querySelector(".print-table").getBoundingClientRect();
    const hd=c.querySelector(".print-head").getBoundingClientRect();
    ok((tb.bottom-hd.top)/cb.height>=0.9,"copy filled "+Math.round((tb.bottom-hd.top)/cb.height*100)+"%");
    ok(tb.bottom<=cb.bottom+1,"table spills out of its frame");
    const cut=[...c.querySelectorAll(".print-table td:not(.label)")].filter(td=>td.scrollWidth>td.clientWidth+1).map(td=>td.textContent);
    eq(cut.join(","),"","values cut short in a copy"); });
  closePrint();
});
await test("fill: a full sheet fills the page height", async()=>{
  await printWith({mode:"single",orientation:"portrait"});
  /* against the page itself, not the sheet: an unsized sheet is only as tall as its table */
  const pageH=sheetBox(printSettings()).h*MMPX;
  const sh=document.querySelector("#printArea .sheet").getBoundingClientRect(), tb=document.querySelector("#printArea .print-table").getBoundingClientRect();
  ok((tb.bottom-sh.top)/pageH>=0.9,"page filled "+Math.round((tb.bottom-sh.top)/pageH*100)+"%");
  closePrint();
});
await test("print: one image of the page, sized to fit any printer's page", async()=>{
  await printWith({mode:"multi",by:"count",copies:5,orientation:"portrait"});
  const img=document.getElementById("printImg"); ok(img&&img.src,"no page image");
  /* decode() never settles for an image that is display:none; wait for it to load instead */
  for(let i=0;i<50&&!(img.complete&&img.naturalWidth);i++) await new Promise(r=>setTimeout(r,50));
  const L=pageLayout(printSettings());
  ok(Math.abs(img.naturalWidth/img.naturalHeight-L.box.w/L.box.h)<0.01,"image is not the page's shape");
  const css=[...document.styleSheets].flatMap(s=>[...s.cssRules]).filter(r=>r.media&&/print/.test(r.media.mediaText)).map(r=>r.cssText).join(" ");
  ok(/#printImg[^}]*max-height:\s*100%/.test(css),"print rule does not cap the image at one page");
  const pdf=await pdfPrepared(); const txt=await pdf.text();
  eq((txt.match(/\/Type \/Page\b(?!s)/g)||[]).length,1,"PDF pages");
  closePrint();
});
await test("print bar: choosing by size shows the cm fields and how many fit", async()=>{
  await printWith({mode:"multi",by:"count",copies:4,orientation:"portrait"});
  document.querySelector('input[name="pvBy"][value="size"]').click(); await tick();
  const w=document.getElementById("pvW"), h=document.getElementById("pvH"); ok(w&&h,"no cm fields");
  w.value="9"; h.value="6"; w.dispatchEvent(new Event("input")); h.dispatchEvent(new Event("input")); await new Promise(r=>setTimeout(r,400));
  ok(/2\s*×\s*4/.test(document.getElementById("printBar").textContent)&&/8/.test(document.getElementById("printBar").textContent),"no '2 × 4 = 8' summary");
  eq(document.querySelectorAll("#printArea .pcopy").length,8,"copies drawn");
  closePrint(); localStorage.removeItem("agenda_print");
});

CFG=JSON.parse(__origCfg);
window.__results=results;
return results;
})();
