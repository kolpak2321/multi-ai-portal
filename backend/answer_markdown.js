(root) => {
  // Read only the answer DOM. Never execute site HTML or include reasoning/UI.
  const skip = 'script,style,button,svg,.thinking-chain-container,.ds-think-content,[aria-hidden="true"],[hidden]';
  const safeUrl = value => { try { const u = new URL(value); return /^https?:$/.test(u.protocol) ? u.href.replace(/\(/g,'%28').replace(/\)/g,'%29') : null; } catch { return null; } };
  const escape = s => s.replace(/([\\`*_[\]<>~])/g,'\\$1');
  const clean = s => s.replace(/[ \t]+\n/g,'\n').replace(/\n{3,}/g,'\n\n').trim();
  function children(e) { return Array.from(e.childNodes).map(render).join(''); }
  function list(e, depth=0) {
    return Array.from(e.children).filter(x=>x.tagName==='LI').map((li,i)=>{
      const prefix=e.tagName==='OL' ? `${Number(e.getAttribute('start')||1)+i}. ` : '- ';
      const body=clean(Array.from(li.childNodes).filter(n=>!['UL','OL'].includes(n.tagName)).map(render).join(''));
      const lines=body.split('\n');
      const item='  '.repeat(depth)+prefix+lines[0]+lines.slice(1).map(l=>'\n'+'  '.repeat(depth)+' '.repeat(prefix.length)+l).join('');
      const nested=Array.from(li.children).filter(n=>['UL','OL'].includes(n.tagName)).map(n=>list(n,depth+1)).join('\n');
      return item+(nested?'\n'+nested:'');
    }).join('\n');
  }
  function render(n) {
    if(n.nodeType===3)return escape(n.textContent.replace(/\s+/g,' '));
    if(n.nodeType!==1)return '';
    if(n.matches(skip)||n.style?.opacity==='0'||n.style?.display==='none')return '';
    const tag=n.tagName;
    if(tag==='PRE'){
      const code=n.querySelector('code')||n;
      const text=code.textContent.replace(/\n$/,'');
      const fence='`'.repeat(Math.max(3,...(text.match(/`+/g)||[]).map(x=>x.length+1)));
      const lang=(code.className.match(/language-([\w+-]+)/)||[])[1]||'';
      return `\n\n${fence}${lang}\n${text}\n${fence}\n\n`;
    }
    if(tag==='CODE'){const text=n.textContent;const fence='`'.repeat(Math.max(1,...(text.match(/`+/g)||[]).map(x=>x.length+1)));return fence+' '+text+' '+fence;}
    if(tag==='A'){
      const url=safeUrl(n.getAttribute('href'));
      const cite=n.querySelector('.ds-markdown-cite');
      const label=cite ? Array.from(cite.querySelectorAll('span')).filter(x=>x.style.opacity!=='0').map(x=>x.textContent).join('').trim() : clean(children(n));
      return url ? (cite?' ':'')+`[${label||url}](${url})` : label;
    }
    if(n.matches('.ds-markdown-cite'))return ' ['+clean(children(n))+']';
    if(tag==='UL'||tag==='OL')return '\n\n'+list(n)+'\n\n';
    if(tag==='TABLE'){
      const rows=Array.from(n.querySelectorAll('tr')).map(tr=>Array.from(tr.children).map(cell=>clean(children(cell)).replace(/\n/g,'<br>').replace(/\|/g,'\\|')));
      if(!rows.length)return '';
      const width=Math.max(...rows.map(r=>r.length));
      const line=r=>'| '+Array.from({length:width},(_,i)=>r[i]||'').join(' | ')+' |';
      return '\n\n'+[line(rows[0]),line(Array(width).fill('---')),...rows.slice(1).map(line)].join('\n')+'\n\n';
    }
    const text=children(n);
    if(/^H[1-6]$/.test(tag))return '\n\n'+'#'.repeat(Number(tag[1]))+' '+text.trim()+'\n\n';
    if(tag==='STRONG'||tag==='B')return '**'+text+'**';
    if(tag==='EM'||tag==='I')return '*'+text+'*';
    if(tag==='DEL'||tag==='S')return '~~'+text+'~~';
    if(tag==='BLOCKQUOTE')return '\n\n'+clean(text).split('\n').map(x=>'> '+x).join('\n')+'\n\n';
    if(tag==='BR')return '  \n';
    if(tag==='HR')return '\n\n---\n\n';
    if(tag==='P'||tag==='DIV'||tag==='SECTION')return '\n\n'+text+'\n\n';
    return text;
  }
  return clean(children(root));
}
