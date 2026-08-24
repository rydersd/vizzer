// Dependency-free, XSS-safe Markdown subset for authored story content.
function mdInlineEscaped(escaped){
  return escaped.split(/(`[^`\n]+`)/).map(part=>{
    if(part.length>2&&part.startsWith('`')&&part.endsWith('`'))
      return '<code>'+part.slice(1,-1)+'</code>';
    let t=part;
    t=t.replace(/\[([^\]\n]+)\]\(([^()\s]+)\)/g,(_m,label,url)=>
      /^https?:\/\//.test(url)
        ?`<a href="${url}" target="_blank" rel="noopener">${label}</a>`
        :`<span class="mdinternal" title="${url}">${label}</span>`);
    t=t.replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>');
    t=t.replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,;:!?])/g,'$1<em>$2</em>');
    t=t.replace(/(^|[\s(])_([^_\n]+)_(?=$|[\s).,;:!?])/g,'$1<em>$2</em>');
    return t;
  }).join('');
}
function mdInline(text){return mdInlineEscaped(esc(text));}

function gherkinCardMarkup(lines){
  const rows=lines.map(line=>{
    const t=line.trim();
    if(!t)return '<div class="ghblank"></div>';
    const head=t.match(/^(Scenario(?: Outline)?|Feature|Background|Examples):\s*(.*)$/i);
    if(head)return `<div class="ghscenario"><span class="ghkw">${esc(head[1])}:</span> <b>${esc(head[2])}</b></div>`;
    const step=t.match(/^(Given|When|Then|And|But)\b\s*(.*)$/i);
    if(step)return `<div class="ghstep"><span class="ghkw">${esc(step[1])}</span> <span>${esc(step[2])}</span></div>`;
    return `<div class="ghline">${esc(t)}</div>`;
  }).join('');
  return `<div class="mdscenario">${rows}</div>`;
}
function gherkinBlocksMarkup(code){
  const groups=[[]];
  for(const line of code.replace(/\s+$/,'').split('\n')){
    if(/^\s*Scenario(?: Outline)?:/i.test(line)&&groups[groups.length-1].some(l=>l.trim()))groups.push([]);
    groups[groups.length-1].push(line);
  }
  return groups.filter(g=>g.some(l=>l.trim())).map(gherkinCardMarkup).join('');
}
function mdListMarkup(items){
  if(!items.length)return '';
  const base=items[0].indent,tag=items[0].ordered?'ol':'ul';
  let html=`<${tag} class="mdlist">`,i=0;
  while(i<items.length){
    const item=items[i],children=[];i++;
    while(i<items.length&&items[i].indent>base){children.push(items[i]);i++;}
    html+=`<li>${mdInline(item.text)}${mdListMarkup(children)}</li>`;
  }
  return html+`</${tag}>`;
}
function mdTableCells(line){
  return line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(cell=>cell.trim());
}
function renderStoryMarkdown(text){
  if(!text)return '';
  const lines=String(text).replace(/\r\n?/g,'\n').split('\n'),out=[];
  const isTableRow=l=>/^\s*\|.*\|\s*$/.test(l);
  const isTableSep=l=>/^\s*\|?[\s:|-]+\|?\s*$/.test(l)&&l.includes('-')&&l.includes('|');
  const listItemRe=/^(\s*)(?:[-*+]|\d+[.)])\s+\S/;
  let i=0;
  while(i<lines.length){
    const line=lines[i];
    if(!line.trim()){i++;continue;}
    const fence=line.match(/^\s*```([\w-]*)\s*$/);
    if(fence){
      const lang=fence[1].toLowerCase(),buffer=[];i++;
      while(i<lines.length&&!/^\s*```\s*$/.test(lines[i])){buffer.push(lines[i]);i++;}
      if(i<lines.length)i++;
      const code=buffer.join('\n');
      out.push(lang==='gherkin'?gherkinBlocksMarkup(code)
        :`<pre class="mdcode"${lang?` data-lang="${esc(lang)}"`:''}>${esc(code)}</pre>`);
      continue;
    }
    const heading=line.match(/^(#{1,6})\s+(.*?)\s*#*\s*$/);
    if(heading){const level=Math.min(6,heading[1].length);out.push(`<div class="mdh mdh${level}">${mdInline(heading[2])}</div>`);i++;continue;}
    if(/^\s*(-{3,}|\*{3,})\s*$/.test(line)){out.push('<hr class="mdhr">');i++;continue;}
    if(/^\s*>/.test(line)){
      const buffer=[];
      while(i<lines.length&&/^\s*>/.test(lines[i])){buffer.push(lines[i].replace(/^\s*>\s?/,''));i++;}
      out.push(`<blockquote class="mdquote">${renderStoryMarkdown(buffer.join('\n'))}</blockquote>`);continue;
    }
    if(isTableRow(line)&&i+1<lines.length&&isTableSep(lines[i+1])){
      const header=mdTableCells(line);i+=2;const body=[];
      while(i<lines.length&&isTableRow(lines[i])){body.push(mdTableCells(lines[i]));i++;}
      out.push('<div class="mdtablewrap"><table class="mdtable"><thead><tr>'
        +header.map(cell=>`<th>${mdInline(cell)}</th>`).join('')+'</tr></thead><tbody>'
        +body.map(row=>'<tr>'+row.map(cell=>`<td>${mdInline(cell)}</td>`).join('')+'</tr>').join('')
        +'</tbody></table></div>');continue;
    }
    if(listItemRe.test(line)){
      const items=[];
      while(i<lines.length){
        const item=lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        if(item){items.push({indent:item[1].length,ordered:/\d/.test(item[2][0]),text:item[3]});i++;}
        else if(lines[i].trim()&&/^\s{2,}/.test(lines[i])&&items.length){items[items.length-1].text+=' '+lines[i].trim();i++;}
        else break;
      }
      out.push(mdListMarkup(items));continue;
    }
    const buffer=[];
    while(i<lines.length&&lines[i].trim()&&!/^\s*(#{1,6}\s|>|```)/.test(lines[i])
        &&!listItemRe.test(lines[i])&&!isTableRow(lines[i])){buffer.push(lines[i].trim());i++;}
    out.push(`<p class="mdp">${mdInline(buffer.join(' '))}</p>`);
  }
  return out.join('');
}
