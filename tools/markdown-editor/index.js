import { remarkStringifyOptionsCtx } from '@milkdown/kit/core';
import { CrepeBuilder } from '@milkdown/crepe/builder';
import { toolbar } from '@milkdown/crepe/feature/toolbar';
import { topBar } from '@milkdown/crepe/feature/top-bar';
import { listItem } from '@milkdown/crepe/feature/list-item';
import { table } from '@milkdown/crepe/feature/table';
import '@milkdown/crepe/theme/common/prosemirror.css';
import '@milkdown/crepe/theme/common/reset.css';
import '@milkdown/crepe/theme/common/toolbar.css';
import '@milkdown/crepe/theme/common/top-bar.css';
import '@milkdown/crepe/theme/common/list-item.css';
import '@milkdown/crepe/theme/common/table.css';
import '@milkdown/crepe/theme/classic-dark.css';

export async function mount(root, original, onChange) {
  let ready=false, dirty=false, baseline='';
  const crepe=new CrepeBuilder({root,defaultValue:original}).addFeature(toolbar).addFeature(topBar).addFeature(listItem).addFeature(table);
  const serialize=markdown=>markdown.replace(/\n+$/,'')+(original.endsWith('\n')?'\n':'');
  const bullet=original.match(/^\s*([-+*]) /m)?.[1]||'-';
  crepe.editor.config(ctx=>ctx.update(remarkStringifyOptionsCtx,options=>({...options,bullet,fences:true})));
  crepe.on(listener=>listener.markdownUpdated((_ctx,markdown)=>{
    if(!ready||markdown===baseline)return;
    baseline=markdown;dirty=true;onChange(serialize(markdown));
  }));
  await crepe.create();baseline=crepe.getMarkdown();ready=true;
  const editable=root.querySelector('[contenteditable]');
  editable?.setAttribute('aria-label','Formatted Markdown editor');
  return {getMarkdown:()=>dirty?serialize(crepe.getMarkdown()):original,normalized:baseline,
    focus:()=>editable?.focus(),setReadonly:value=>crepe.setReadonly(value),destroy:()=>{ready=false;return crepe.destroy();}};
}
