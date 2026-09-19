(() => {
const KEY='wafer-watch-theme';
let stored=null;try{stored=localStorage.getItem(KEY);}catch(e){}
const media=window.matchMedia('(prefers-color-scheme: light)');
const initial=stored||'light';
function paint(theme){
 document.documentElement.setAttribute('data-theme',theme);
 const btn=document.getElementById('theme-toggle');
 if(btn){btn.setAttribute('aria-pressed',String(theme==='light'));btn.querySelector('.icon').textContent=theme==='light'?'☾':'☀';btn.querySelector('.label').textContent=theme==='light'?'Dark':'Light';}
}
paint(initial);
window.dashboardTheme={
 get:()=>document.documentElement.getAttribute('data-theme')||'dark',
 set(theme){try{localStorage.setItem(KEY,theme);}catch(e){}paint(theme);window.dispatchEvent(new CustomEvent('themechange',{detail:{theme}}));},
 toggle(){window.dashboardTheme.set(window.dashboardTheme.get()==='light'?'dark':'light');},
 color(name,fallback){const v=getComputedStyle(document.documentElement).getPropertyValue(name).trim();return v||fallback||'';}
};
document.addEventListener('DOMContentLoaded',()=>{
 const btn=document.getElementById('theme-toggle');
 if(btn)btn.onclick=()=>window.dashboardTheme.toggle();
 paint(window.dashboardTheme.get());
});
try{media.addEventListener('change',e=>{if(!stored)window.dashboardTheme.set(e.matches?'light':'dark');});}catch(e){}
})();
