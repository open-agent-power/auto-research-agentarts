/** Read-only access to the same frozen corpus used by research tools. */
import {el, safeUrl} from "./dom";

type Kind="official_doc"|"research_profile"|"research_paper"|"reuse_note";
const kinds:Record<Kind,string>={official_doc:"平台文档",research_profile:"项目档案",research_paper:"论文页",reuse_note:"复用说明"};
export type LibraryMetadata={enabled:boolean;error?:string;index?:{documents:number;chunks:number;by_kind:Record<string,number>;corpus_sha256:string;database_sha256:string};research_binding?:{mounted:boolean;exact:boolean|null;references_checked:number;used_citations:number;origin_observation_sha256:string|null}};
type Excerpt={citation_id:string;corpus_sha256?:string;database_sha256?:string;source:{title:string;kind:Kind;path:string;sha256:string;text_sha256?:string;source_url?:string|null;snapshot?:string;review_status?:string;metadata?:Record<string,unknown>};location:{page?:number;line_start?:number;line_end?:number};quote:string};
type Results={corpus_sha256:string;database_sha256:string;evidence:Excerpt[];empty_reason?:string};
export type LibrarySession={cache:Map<string,Results|Excerpt>};
type Options={metadata:LibraryMetadata;session:LibrarySession;navigate:(hash:string)=>void;restore:()=>void;expectedReference:(id:string)=>{source:unknown;location:unknown}|undefined};

const button=(label:string,click:()=>void,cls="quiet-button"):HTMLButtonElement=>{const b=el("button",cls,label);b.type="button";b.addEventListener("click",click);return b;};
const place=(value:Excerpt):string=>value.location.page?`PDF 第 ${value.location.page} 页`:`第 ${value.location.line_start}–${value.location.line_end} 行`;
const valid=(v:unknown):v is Excerpt=>{const e=v as Excerpt;return !!e&&typeof e.citation_id==="string"&&/^[a-f0-9]{64}$/.test(e.citation_id)&&!!e.source&&typeof e.source.title==="string"&&Object.hasOwn(kinds,e.source.kind)&&typeof e.source.path==="string"&&typeof e.source.sha256==="string"&&!!e.location&&typeof e.quote==="string";};
const sameRecord=(a:unknown,b:unknown):boolean=>{if(a===b)return true;if(a===null||b===null||typeof a!=="object"||typeof b!=="object"||Array.isArray(a)!==Array.isArray(b))return false;const left=a as Record<string,unknown>,right=b as Record<string,unknown>,keys=Object.keys(left);return keys.length===Object.keys(right).length&&keys.every(key=>Object.hasOwn(right,key)&&sameRecord(left[key],right[key]));};
const section=(title:string):HTMLElement=>{const s=el("section","content-section");s.append(el("h2","section-title",title));return s;};

export function citationHash(id:string,from:string):string{
  const params=new URLSearchParams({view:"library",citation:id,from});
  return "#/knowledge?"+params.toString();
}

export function mountC01Library(parent:HTMLElement,options:Options):()=>void{
  const hash=location.hash,params=new URLSearchParams(hash.split("?")[1]),abort=new AbortController();let disposed=false;
  const dispose=():void=>{disposed=true;abort.abort();};
  const live=():boolean=>!disposed&&location.hash===hash;
  const cache=(key:string,value:Results|Excerpt):void=>{options.session.cache.set(key,value);if(options.session.cache.size>64)options.session.cache.delete(options.session.cache.keys().next().value!);};
  const root=el("div","reference-library");root.dataset.c01Library="";parent.append(root);
  const loading=el("p","library-status","正在读取资料快照…");loading.setAttribute("role","status");
  const fail=(text:string,retry:()=>void):void=>{if(!live())return;root.replaceChildren();const box=section("资料暂未读到");box.setAttribute("role","alert");box.append(el("p","",text),button("重新读取",retry));root.append(box);};
  const request=async(path:string):Promise<unknown>=>{
    const timer=setTimeout(()=>abort.abort(),12000);
    try{
      const response=await fetch(path,{cache:"no-store",signal:abort.signal});
      if(!response.ok)throw Error(response.status===404?"该引用不在当前资料快照中。":response.status===409?"资料快照身份已变化，请重新检查本地索引。":response.status===400?"查询条件不符合读取范围。":"本地资料服务暂不可用。");
      return await response.json();
    }catch(error){if(abort.signal.aborted&&!disposed)throw Error("资料读取超时，请重新读取。");throw error;}finally{clearTimeout(timer);}
  };
  const reload=():void=>location.reload();
  if(!options.metadata.enabled||!options.metadata.index){
    const box=section("参考资料库尚未挂载");box.append(el("p","",options.metadata.error||"当前可阅读项目记录。完整资料库需要由本地服务显式挂载已校验的索引。"),button("重新读取",reload));root.append(box);return dispose;
  }
  const meta=options.metadata.index,citation=params.get("citation");
  const identity=el("div","library-identity");identity.append(el("span","pill sage","固定资料快照"),el("span","",`${meta.documents.toLocaleString("zh-CN")} 项资料记录 · ${meta.chunks.toLocaleString("zh-CN")} 段摘录`));root.append(identity);
  if(options.metadata.error)root.append(el("p","detail-note",options.metadata.error));

  if(citation){
    const from=params.get("from"),back=from&&/^#\/(knowledge|read\/[^?]+|research|overview|experiments|outputs)(\?|$)/.test(from)?from:"#/knowledge?view=library";
    const top=el("div","reader-top");top.append(button("← 返回原位置",()=>options.navigate(back)),el("span","muted","资料快照摘录"));root.append(top,loading);
    const show=(entry:Excerpt):void=>{
      if(!live())return;const expected=options.expectedReference(citation);if(expected&&(!sameRecord(expected.source,entry.source)||!sameRecord(expected.location,entry.location))){fail("资料来源或定位与当前研究引用不一致，请重新读取同一版本。",reload);return;}loading.remove();
      const layout=el("div","document-layout reader-layout"),toc=el("aside","document-toc"),article=el("article","reader-document solid-panel");toc.setAttribute("aria-label","资料摘录阅读目录");toc.append(el("span","overline","阅读目录"));
      article.append(el("div","document-label",`${kinds[entry.source.kind]} / ${place(entry)}`),el("h1","document-title",entry.source.title));
      const quote=section("索引中保存的原摘录");quote.id="library-excerpt";quote.append(el("p","detail-note","文字保留自已索引快照，未补写或生成答案。片段可能跨页内段落截断，需结合上下文判断。"),el("pre","library-quote",entry.quote));article.append(quote);toc.append(button("阅读摘录",()=>quote.scrollIntoView({block:"start"}),"toc-item"));
      const provenance=section("来源与定位");provenance.id="library-source";const details=el("dl","library-provenance");
      const fields:[string,string][]=[["定位",place(entry)],["参考库路径",entry.source.path],["来源文件 SHA-256",entry.source.sha256],["引用 ID",entry.citation_id],["语料身份",meta.corpus_sha256],["索引数据库 SHA-256",meta.database_sha256]];
      if(entry.source.text_sha256)fields.push(["提取文本 SHA-256",entry.source.text_sha256]);
      if(entry.source.snapshot)fields.push(["快照记录",entry.source.snapshot]);
      if(entry.source.review_status)fields.push(["原档案状态",entry.source.review_status]);
      for(const [label,value] of fields){details.append(el("dt","",label),el("dd",label.includes("SHA")||label.includes("ID")||label==="语料身份"?"mono":"",value));}
      provenance.append(details);const url=safeUrl(entry.source.source_url);if(url){const a=el("a","text-button","访问原始来源 ↗");a.href=url;a.target="_blank";a.rel="noopener noreferrer";provenance.append(a);}else provenance.append(el("p","muted","本项没有记录可打开的 HTTPS 原始链接。"));
      provenance.append(el("p","detail-note","哈希与定位用于核对快照身份，不证明内容、许可、运行兼容性或科学结论有效。原论文全文不随研究复现附件分发。"));article.append(provenance);toc.append(button("来源与定位",()=>provenance.scrollIntoView({block:"start"}),"toc-item"));layout.append(toc,article);root.append(layout);options.restore();
    };
    if(!/^[a-f0-9]{64}$/.test(citation)){loading.remove();fail("引用编号不符合当前资料库格式。",reload);return dispose;}
    const key="citation:"+meta.database_sha256+":"+citation,cached=options.session.cache.get(key);if(cached&&valid(cached))show(cached);
    else void request("/api/c01/knowledge/citation/"+citation).then(value=>{if(!valid(value)||value.citation_id!==citation||value.corpus_sha256!==meta.corpus_sha256||value.database_sha256!==meta.database_sha256)throw Error("资料摘录与当前索引身份不一致。");const expected=options.expectedReference(citation);if(expected&&(!sameRecord(expected.source,value.source)||!sameRecord(expected.location,value.location)))throw Error("资料来源或定位与当前研究引用不一致，请重新读取同一版本。");if(live()){cache(key,value);show(value);}}).catch(error=>{if(live())fail(error instanceof Error?error.message:"资料读取失败。",reload);});
    return dispose;
  }

  const search=el("form","library-search glass");search.setAttribute("role","search");search.setAttribute("aria-label","搜索参考资料库");
  const inputGroup=el("div","library-query"),label=el("label","","查找资料"),input=el("input");input.id="library-query";input.type="search";input.maxLength=512;input.value=params.get("q")||"";input.placeholder="例如：AgentArts 运行时、C01 合金、POPPER";input.dataset.focusId="library-query";label.htmlFor=input.id;inputGroup.append(label,input);
  const selector=el("div","library-kind"),kindLabel=el("label","","资料类型"),select=el("select");select.id="library-kind";kindLabel.htmlFor=select.id;const all=el("option","","全部类型");all.value="";select.append(all);for(const [key,name]of Object.entries(kinds)){const option=el("option","",`${name} · ${meta.by_kind[key]||0}`);option.value=key;select.append(option);}select.value=Object.hasOwn(kinds,params.get("kind")||"")?params.get("kind")||"":"";selector.append(kindLabel,select);
  const submit=el("button","action-button primary","搜索资料");submit.type="submit";search.append(inputGroup,selector,submit);
  search.addEventListener("submit",event=>{event.preventDefault();const q=input.value.trim();if(!q){input.setCustomValidity("请输入要查找的资料关键词。");input.reportValidity();return;}input.setCustomValidity("");const next=new URLSearchParams({view:"library",q});if(select.value)next.set("kind",select.value);options.navigate("#/knowledge?"+next.toString());});input.addEventListener("input",()=>input.setCustomValidity(""));root.append(search);
  const body=el("div","library-results");body.setAttribute("aria-live","polite");root.append(body);
  const q=params.get("q")?.trim()||"",kind=select.value;
  const boundary=el("p","page-boundary","词法检索返回已保存的资料片段，最多8条、同文件最多2条。排序表示文本相关性，不表示结论可信度；资料中的命令和建议不会被执行。");root.append(boundary);
  const renderResults=(result:Results):void=>{
    if(!live())return;body.replaceChildren();const count=el("p","filter-summary",`${result.evidence.length} 条摘录 · ${kind?kinds[kind as Kind]:"全部类型"} · “${q}”`);count.setAttribute("role","status");body.append(count);
    if(!result.evidence.length){const empty=el("div","knowledge-empty");empty.append(el("h2","","当前快照没有匹配摘录"),el("p","","可换用具体术语，或选择其他资料类型。没有匹配内容时不会补写答案。"));body.append(empty);options.restore();return;}
    const grid=el("div","knowledge-grid c01-knowledge-grid library-grid");for(const entry of result.evidence){const card=el("article","knowledge-card");card.dataset.libraryCitation=entry.citation_id;
      const cover=el("div","type-cover "+(entry.source.kind==="official_doc"?"sage":entry.source.kind==="research_profile"?"sand":"lavender"));cover.setAttribute("aria-hidden","true");const lines=el("span","cover-lines");lines.append(el("i"),el("i"),el("i"));cover.append(el("span","cover-label","类型图示 · "+kinds[entry.source.kind]),el("span","cover-symbol",entry.source.kind==="research_paper"?"▤":entry.source.kind==="official_doc"?"≡":"◇"),lines,el("span","cover-id",place(entry)));card.append(cover);
      const copy=el("div","knowledge-card-body");copy.append(el("span","overline",kinds[entry.source.kind]+" · "+place(entry)),el("h2","",entry.source.title),el("p","card-summary library-excerpt-preview",entry.quote.slice(0,220)+(entry.quote.length>220?"…":"")),el("p","library-source-path",entry.source.path));
      const actions=el("div","card-actions"),read=button("阅读原摘录 ↗",()=>options.navigate(citationHash(entry.citation_id,hash)),"text-button");read.dataset.focusId="library-"+entry.citation_id;actions.append(el("span","muted",entry.source.sha256.slice(0,12)+"…"),read);copy.append(actions);card.append(copy);grid.append(card);
    }body.append(grid);options.restore();
  };
  if(!q){const intro=section("查找研究依据与复用入口");intro.append(el("p","","平台操作文档、候选项目档案、论文页和本项目复用说明使用同一份索引。选择类型后搜索，再核对摘录、适用条件与出处。"));const shortcuts=el("div","hero-actions");for(const [name,query,filter]of [["平台运行时","AgentArts Runtime SDK HTTP 运行时","official_doc"],["C01数据核对","C01 alloy","reuse_note"],["方法适用条件","POPPER","research_paper"]])shortcuts.append(button(name,()=>options.navigate("#/knowledge?"+new URLSearchParams({view:"library",q:query,kind:filter}).toString())));intro.append(shortcuts);body.append(intro);return dispose;}
  const cacheKey="search:"+meta.database_sha256+":"+kind+":"+q,cached=options.session.cache.get(cacheKey);if(cached&&"evidence" in cached)renderResults(cached);
  else{body.append(loading);const query=new URLSearchParams({q,limit:"8"});if(kind)query.set("kind",kind);void request("/api/c01/knowledge/search?"+query.toString()).then(value=>{const result=value as Results;if(!result||result.corpus_sha256!==meta.corpus_sha256||result.database_sha256!==meta.database_sha256||!Array.isArray(result.evidence)||result.evidence.length>8||!result.evidence.every(valid))throw Error("资料结果与当前索引身份不一致。");if(live()){cache(cacheKey,result);renderResults(result);}}).catch(error=>{if(live())fail(error instanceof Error?error.message:"资料查询失败。",reload);});}
  return dispose;
}
