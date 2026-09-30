"""
Stage 4: A2UI JSON → Mobile-style HTML
Pure Python, No API calls needed.

IMPROVEMENTS vs original:
- Style-aware rendering: reads category style from a2ui JSON
- Per-style CSS themes: Spotify dark, Amazon white+orange, Airbnb pink,
  Google Maps blue, Swiggy orange, Notion minimal, default minimal
- Mobile phone frame: 390px wide, rounded corners, scrollable — looks like a real app
- Pseudo-table rendering: Column of Rows with weighted Texts rendered as proper table
- AppBar uses style bg color not just primary
- Badge, Chip, Button use style accent colors
- Card uses style surface color + elevation shadow
- BottomNavigation pinned to bottom of phone frame
"""
import os, json, argparse
from config import CATEGORIES, A2UI_JSON_DIR, HTML_DIR, CATEGORY_STYLES, STYLE_TOKENS

ICON_MAP = {
    "star":"⭐","check":"✅","close":"❌","search":"🔍","home":"🏠","settings":"⚙️",
    "info":"ℹ️","warning":"⚠️","camera":"📷","download":"⬇️","edit":"✏️","delete":"🗑️",
    "share":"📤","favorite":"❤️","mail":"📧","phone":"📞","person":"👤","location-on":"📍",
    "calendar":"📅","play":"▶️","pause":"⏸️","stop":"⏹️","volume-up":"🔊",
    "cart":"🛒","payment":"💳","add":"➕","refresh":"🔄","send":"📨",
    "bell":"🔔","menu":"☰","upload":"⬆️","folder":"📁","help":"❓",
    "house":"🏠","bookmark":"🔖","map":"🗺️","music-note":"🎵","film":"🎬",
}

TABS_JS = """
function showTab(tid,idx){
  var i=0;while(true){var p=document.getElementById(tid+'_p_'+i),b=document.getElementById(tid+'_b_'+i);
  if(!p)break;p.classList.toggle('hidden',i!==idx);
  if(i===idx){b.setAttribute('data-active','1');}
  else{b.removeAttribute('data-active');}i++;}}

var _slideIdx={};
function showSlide(cid,idx,total){
  if(!_slideIdx[cid])_slideIdx[cid]=0;
  if(idx===-1)_slideIdx[cid]=(_slideIdx[cid]-1+total)%total;
  else if(idx===-2)_slideIdx[cid]=(_slideIdx[cid]+1)%total;
  else _slideIdx[cid]=idx;
  for(var i=0;i<total;i++){
    var s=document.getElementById(cid+'_s_'+i),dot=document.getElementById(cid+'_dot_'+i);
    if(s)s.style.display=(i===_slideIdx[cid])?'block':'none';
    if(dot)dot.className='w-2 h-2 rounded-full '+(i===_slideIdx[cid]?'bg-blue-500':'bg-gray-400');
  }
}
"""

# ── Per-style CSS ──────────────────────────────────────────────────────────────
STYLE_CSS = {
    "spotify": """
      .phone-wrap{background:#121212;color:#FFFFFF;}
      .s-card{background:#1E1E1E;border:none;border-radius:12px;padding:14px;box-shadow:0 2px 8px rgba(0,0,0,0.6);}
      .s-text-primary{color:#FFFFFF;}
      .s-text-secondary{color:#B3B3B3;}
      .s-appbar{background:#000000;color:#FFFFFF;}
      .s-badge{background:#1DB954;}
      .s-chip{background:#282828;color:#FFFFFF;border:1px solid #444;}
      .s-btn-primary{background:#1DB954;color:#000;border-radius:24px;font-weight:700;}
      .s-btn-default{background:#282828;color:#FFFFFF;border-radius:24px;}
      .s-btn-borderless{color:#1DB954;}
      .s-divider{border-color:#282828;}
      .s-bottom-nav{background:#000000;border-top:1px solid #282828;}
    """,
    "amazon": """
      .phone-wrap{background:#FFFFFF;color:#0F1111;}
      .s-card{background:#FFFFFF;border:1px solid #DDD;border-radius:8px;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,0.08);}
      .s-text-primary{color:#0F1111;}
      .s-text-secondary{color:#565959;}
      .s-appbar{background:#232F3E;color:#FFFFFF;}
      .s-badge{background:#FF9900;color:#000;}
      .s-chip{background:#F7F8F8;color:#0F1111;border:1px solid #DDD;}
      .s-btn-primary{background:#FFD814;color:#0F1111;border-radius:4px;font-weight:600;}
      .s-btn-default{background:#F0F2F2;color:#0F1111;border-radius:4px;}
      .s-btn-borderless{color:#007185;}
      .s-divider{border-color:#E7E7E7;}
      .s-bottom-nav{background:#FFFFFF;border-top:1px solid #DDD;}
    """,
    "airbnb": """
      .phone-wrap{background:#FFFFFF;color:#222222;}
      .s-card{background:#FFFFFF;border:1px solid #EBEBEB;border-radius:16px;padding:0;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.10);}
      .s-text-primary{color:#222222;}
      .s-text-secondary{color:#717171;}
      .s-appbar{background:#FFFFFF;color:#222222;border-bottom:1px solid #EBEBEB;}
      .s-badge{background:#FF385C;color:#FFF;}
      .s-chip{background:#F7F7F7;color:#222;border:1px solid #EBEBEB;border-radius:24px;}
      .s-btn-primary{background:#FF385C;color:#FFF;border-radius:8px;font-weight:600;}
      .s-btn-default{background:#FFFFFF;color:#222;border:1px solid #222;border-radius:8px;}
      .s-btn-borderless{color:#222222;text-decoration:underline;}
      .s-divider{border-color:#EBEBEB;}
      .s-bottom-nav{background:#FFFFFF;border-top:1px solid #EBEBEB;}
    """,
    "maps": """
      .phone-wrap{background:#FFFFFF;color:#202124;}
      .s-card{background:#FFFFFF;border:none;border-radius:12px;padding:14px;box-shadow:0 1px 6px rgba(32,33,36,0.18);}
      .s-text-primary{color:#202124;}
      .s-text-secondary{color:#70757A;}
      .s-appbar{background:#FFFFFF;color:#202124;border-bottom:1px solid #E8EAED;}
      .s-badge{background:#1A73E8;color:#FFF;}
      .s-chip{background:#E8F0FE;color:#1A73E8;border:none;border-radius:16px;}
      .s-btn-primary{background:#1A73E8;color:#FFF;border-radius:24px;}
      .s-btn-default{background:#FFFFFF;color:#1A73E8;border:1px solid #DADCE0;border-radius:24px;}
      .s-btn-borderless{color:#1A73E8;}
      .s-divider{border-color:#E8EAED;}
      .s-bottom-nav{background:#FFFFFF;border-top:1px solid #E8EAED;}
    """,
    "swiggy": """
      .phone-wrap{background:#FFFFFF;color:#282C3F;}
      .s-card{background:#FFFFFF;border:1px solid #F0F0F5;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(40,44,63,0.06);}
      .s-text-primary{color:#282C3F;}
      .s-text-secondary{color:#93959F;}
      .s-appbar{background:#FC8019;color:#FFFFFF;}
      .s-badge{background:#FC8019;color:#FFF;}
      .s-chip{background:#FFF5EE;color:#FC8019;border:1px solid #FFD9B3;border-radius:4px;}
      .s-btn-primary{background:#FC8019;color:#FFF;border-radius:4px;font-weight:700;}
      .s-btn-default{background:#FFFFFF;color:#282C3F;border:1px solid #D4D5D9;border-radius:4px;}
      .s-btn-borderless{color:#FC8019;}
      .s-divider{border-color:#F0F0F5;}
      .s-bottom-nav{background:#FFFFFF;border-top:2px solid #FC8019;}
    """,
    "notion": """
      .phone-wrap{background:#FFFFFF;color:#37352F;}
      .s-card{background:#FFFFFF;border:1px solid #E9E9E7;border-radius:4px;padding:14px;box-shadow:none;}
      .s-text-primary{color:#37352F;}
      .s-text-secondary{color:#787774;}
      .s-appbar{background:#FFFFFF;color:#37352F;border-bottom:1px solid #E9E9E7;}
      .s-badge{background:#E3F2FD;color:#2383E2;border-radius:4px;}
      .s-chip{background:#F1F1EF;color:#37352F;border:none;border-radius:4px;}
      .s-btn-primary{background:#2383E2;color:#FFF;border-radius:4px;}
      .s-btn-default{background:#F1F1EF;color:#37352F;border-radius:4px;}
      .s-btn-borderless{color:#2383E2;}
      .s-divider{border-color:#E9E9E7;}
      .s-bottom-nav{background:#FBFBFA;border-top:1px solid #E9E9E7;}
    """,
    "minimal": """
      .phone-wrap{background:#FFFFFF;color:#1E293B;}
      .s-card{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;padding:14px;box-shadow:0 1px 4px rgba(0,0,0,0.06);}
      .s-text-primary{color:#1E293B;}
      .s-text-secondary{color:#64748B;}
      .s-appbar{background:#2563EB;color:#FFFFFF;}
      .s-badge{background:#2563EB;color:#FFF;}
      .s-chip{background:#EFF6FF;color:#2563EB;border:1px solid #BFDBFE;border-radius:16px;}
      .s-btn-primary{background:#2563EB;color:#FFF;border-radius:8px;}
      .s-btn-default{background:#F1F5F9;color:#1E293B;border-radius:8px;}
      .s-btn-borderless{color:#2563EB;}
      .s-divider{border-color:#E2E8F0;}
      .s-bottom-nav{background:#FFFFFF;border-top:1px solid #E2E8F0;}
    """,
}


class Renderer:
    def __init__(self, comps, primary="#2563EB", style="minimal"):
        self.m       = {c["id"]: c for c in comps if "id" in c}
        self.primary = primary
        self.style   = style
        self.tokens  = STYLE_TOKENS.get(style, STYLE_TOKENS["minimal"])
        self.accent  = self.tokens.get("accent", primary)
        self.done    = set()

    def r(self, cid, d=0):
        if not cid or cid not in self.m or cid in self.done: return ""
        self.done.add(cid)
        c = self.m[cid]
        t = c.get("component", "")

        if t == "Column":
            ch = "\n".join(self.r(x, d+1) for x in c.get("children", []))
            return f'<div class="flex flex-col gap-3">{ch}</div>'

        elif t == "Row":
            ch = "\n".join(self.r(x, d+1) for x in c.get("children", []))
            align = "items-start" if c.get("align") == "start" else "items-center"
            return f'<div class="flex flex-row gap-2 {align} flex-wrap">{ch}</div>'

        elif t == "Text":
            txt = self.e(c.get("text", ""))
            v   = c.get("variant", "body")
            w   = f' style="flex:{c["weight"]};min-width:0"' if c.get("weight") else ""
            clr = "s-text-primary" if v in ("h1","h2","h3","h4") else "s-text-secondary"
            styles = {
                "h1":      f'<h1 class="text-2xl font-bold {clr}"{w}>{txt}</h1>',
                "h2":      f'<h2 class="text-xl font-bold {clr}"{w}>{txt}</h2>',
                "h3":      f'<h3 class="text-lg font-semibold {clr}"{w}>{txt}</h3>',
                "h4":      f'<h4 class="text-base font-semibold {clr}"{w}>{txt}</h4>',
                "body":    f'<p class="text-sm {clr} leading-relaxed"{w}>{txt}</p>',
                "caption": f'<span class="text-xs s-text-secondary"{w}>{txt}</span>',
                "overline":f'<span class="text-xs font-semibold uppercase tracking-wide s-text-secondary"{w}>{txt}</span>',
            }
            return styles.get(v, f'<p class="text-sm {clr}"{w}>{txt}</p>')

        elif t == "Image":
            url = c.get("url", "")
            v   = c.get("variant", "mediumFeature")
            fit = c.get("fit", "cover")
            h   = {"icon":"32px","avatar":"44px","square":"160px","smallFeature":"120px",
                   "mediumFeature":"200px","largeFeature":"280px","header":"180px"}.get(v,"200px")
            if v in ("icon", "avatar"):
                radius = "50%" if v == "avatar" else "6px"
                return f'<img src="{url}" style="width:{h};height:{h};object-fit:{fit};border-radius:{radius};flex-shrink:0" onerror="this.style.display=\'none\'">'
            return f'<img src="{url}" class="w-full rounded-lg" style="height:{h};object-fit:{fit}" onerror="this.style.display=\'none\'">'

        elif t == "Icon":
            name = c.get("name", c.get("icon", "star"))
            em   = ICON_MAP.get(name, "•")
            url  = c.get("url", "")
            if url and "bootstrap-icons" in url:
                return f'<img src="{url}" style="width:20px;height:20px;flex-shrink:0" onerror="this.innerHTML=\'•\'">'
            return f'<span style="font-size:18px;line-height:1">{em}</span>'

        elif t == "Divider":
            return '<hr class="s-divider my-2">'

        elif t == "Card":
            ch = self.r(c.get("child", ""), d+1)
            return f'<div class="s-card">{ch}</div>'

        elif t == "Button":
            ch  = self.r(c.get("child", ""), d+1)
            v   = c.get("variant", "default")
            url = c.get("action", {}).get("functionCall", {}).get("args", {}).get("url", "#")
            cls = {"primary":"s-btn-primary","default":"s-btn-default",
                   "borderless":"s-btn-borderless","ghost":"s-btn-borderless",
                   "outlined":"s-btn-default","rounded":"s-btn-primary",
                   "pill":"s-btn-primary","cta":"s-btn-primary"}.get(v, "s-btn-default")
            base = "inline-flex items-center gap-1 px-4 py-2 text-sm font-medium cursor-pointer transition-opacity hover:opacity-80"
            return f'<a href="{url}" target="_blank" class="{base} {cls}">{ch}</a>'

        elif t == "Badge":
            lbl   = self.e(c.get("label", c.get("text", "")))
            color = c.get("color", self.accent)
            # Detect if light badge (notion style)
            txt_color = "#000" if self.style == "notion" else "#FFF"
            return f'<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold" style="background:{color};color:{txt_color}">{lbl}</span>'

        elif t in ("Chip", "Tag"):
            lbl = self.e(c.get("label", c.get("text", "")))
            sel = c.get("selected", False)
            extra = f' style="background:{self.accent};color:#fff"' if sel else ""
            return f'<span class="s-chip inline-flex items-center px-3 py-1 rounded-full text-xs font-medium"{extra}>{lbl}</span>'

        elif t == "AppBar":
            title    = self.e(c.get("title", ""))
            subtitle = self.e(c.get("subtitle", ""))
            sub_html = f'<p class="text-xs opacity-75 mt-0.5">{subtitle}</p>' if subtitle else ""
            bg       = c.get("backgroundColor", self.tokens.get("bg", self.primary))
            txt_col  = "#FFFFFF" if self.style in ("spotify","swiggy","minimal","maps") else self.tokens.get("text_primary","#FFFFFF")
            return (f'<div class="s-appbar px-4 py-3 flex items-center gap-3 sticky top-0 z-10" style="background:{bg};color:{txt_col}">'
                    f'<div class="flex-1"><h1 class="text-base font-bold leading-tight" style="color:{txt_col}">{title}</h1>{sub_html}</div></div>')

        elif t == "BottomNavigation":
            items     = c.get("items", [])
            nav_items = ""
            for item in items:
                icon  = ICON_MAP.get(item.get("icon", ""), item.get("icon", "•"))
                label = self.e(item.get("label", ""))
                sel   = item.get("selected", False)
                color = self.accent if sel else self.tokens.get("text_secondary","#64748B")
                nav_items += (
                    f'<button class="flex flex-col items-center gap-0.5 flex-1 py-2 text-xs font-medium" '
                    f'style="color:{color}">'
                    f'<span style="font-size:20px">{icon}</span>'
                    f'<span>{label}</span></button>'
                )
            return (f'<div class="s-bottom-nav flex sticky bottom-0 z-10">{nav_items}</div>'
                    f'<div style="height:56px"></div>')

        elif t == "ProgressBar":
            val   = min(100, max(0, int(c.get("value", 0))))
            lbl   = self.e(c.get("label", ""))
            color = c.get("color", self.accent)
            return (f'<div class="flex flex-col gap-1">'
                    f'<div class="flex justify-between text-xs s-text-secondary">'
                    f'<span>{lbl}</span><span>{val}%</span></div>'
                    f'<div class="w-full rounded-full h-2" style="background:{self.tokens.get("surface","#F1F5F9")}">'
                    f'<div class="h-2 rounded-full transition-all" style="width:{val}%;background:{color}"></div>'
                    f'</div></div>')

        elif t == "Stepper":
            steps  = c.get("steps", [])
            active = c.get("activeStep", 0)
            items  = ""
            for idx, step in enumerate(steps):
                is_done   = idx < active
                is_active = idx == active
                circle_bg = self.accent if is_active else ("#22C55E" if is_done else self.tokens.get("surface","#E2E8F0"))
                circle_cl = "#FFF" if (is_active or is_done) else self.tokens.get("text_secondary","#64748B")
                icon      = "✓" if is_done else str(idx + 1)
                line      = f'<div class="w-px h-5 mx-auto my-0.5" style="background:{self.tokens.get("surface","#E2E8F0")}"></div>' if idx < len(steps)-1 else ""
                items += (
                    f'<div class="flex items-start gap-3">'
                    f'<div class="flex flex-col items-center">'
                    f'<div class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold" '
                    f'style="background:{circle_bg};color:{circle_cl}">{icon}</div>'
                    f'{line}</div>'
                    f'<div class="pt-0.5 pb-3">'
                    f'<p class="text-sm font-medium s-text-primary">{self.e(step.get("title",""))}</p>'
                    f'<p class="text-xs s-text-secondary mt-0.5">{self.e(step.get("description",""))}</p>'
                    f'</div></div>'
                )
            return f'<div class="flex flex-col">{items}</div>'

        elif t == "Tabs":
            tabs  = c.get("tabs", [])
            tid   = f"t_{cid.replace('-','_')}"
            btns  = ""
            for i, tb in enumerate(tabs):
                active_style = f'style="background:{self.accent};color:#fff"' if i == 0 else ""
                btns += (f'<button onclick="showTab(\'{tid}\',{i})" id="{tid}_b_{i}" '
                         f'class="px-3 py-1.5 text-xs font-medium rounded-full s-chip" {active_style}>'
                         f'{self.e(tb.get("title",""))}</button>')
            panels = "".join(
                f'<div id="{tid}_p_{i}" class="{"" if i==0 else "hidden "}mt-3">{self.r(tb.get("child",""),d+1)}</div>'
                for i, tb in enumerate(tabs)
            )
            return f'<div><div class="flex gap-2 flex-wrap mb-1 overflow-x-auto">{btns}</div>{panels}</div>'

        elif t == "Map":
            loc   = self.e(c.get("location", c.get("center", "India")))
            zoom  = c.get("zoom", 13)
            query = loc.replace(" ", "+")
            return (f'<div class="rounded-xl overflow-hidden" style="height:220px">'
                    f'<iframe width="100%" height="100%" frameborder="0" style="border:0" '
                    f'src="https://maps.google.com/maps?q={query}&z={zoom}&output=embed" '
                    f'allowfullscreen loading="lazy"></iframe></div>')

        elif t == "TextField":
            lbl = self.e(c.get("label", ""))
            v   = c.get("variant", "shortText")
            inp = (f'<textarea class="border rounded-lg px-3 py-2 w-full resize-none text-sm" rows="3" placeholder="{lbl}"></textarea>'
                   if v == "longText" else
                   f'<input type="text" placeholder="{lbl}" class="border rounded-lg px-3 py-2 w-full text-sm">')
            return f'<div class="flex flex-col gap-1"><label class="text-xs font-medium s-text-secondary">{lbl}</label>{inp}</div>'

        elif t == "CheckBox":
            lbl = self.e(c.get("label", ""))
            chk = "checked" if c.get("value") else ""
            return f'<label class="flex items-center gap-2 cursor-pointer text-sm s-text-primary"><input type="checkbox" {chk} class="w-4 h-4">{lbl}</label>'

        elif t == "Switch":
            lbl = self.e(c.get("label", ""))
            chk = "checked" if c.get("value") else ""
            sid = f"sw_{cid.replace('-','_')}"
            return (f'<label class="flex items-center justify-between cursor-pointer py-1">'
                    f'<span class="text-sm s-text-primary">{lbl}</span>'
                    f'<div class="relative"><input type="checkbox" id="{sid}" {chk} class="sr-only peer">'
                    f'<div class="w-10 h-5 bg-gray-300 rounded-full peer '
                    f'peer-checked:bg-blue-500 after:content-[\'\'] after:absolute after:top-0.5 '
                    f'after:left-0.5 after:bg-white after:rounded-full after:h-4 after:w-4 '
                    f'after:transition-all peer-checked:after:translate-x-5"></div></div></label>')

        elif t == "Slider":
            lbl = self.e(c.get("label",""))
            val = c.get("value", 50)
            mn  = c.get("min", 0)
            mx  = c.get("max", 100)
            sid = f"s_{cid.replace('-','_')}"
            return (f'<div class="flex flex-col gap-1">'
                    f'<label class="text-xs font-medium s-text-secondary">{lbl}: <span id="{sid}">{val}</span></label>'
                    f'<input type="range" min="{mn}" max="{mx}" value="{val}" class="w-full" '
                    f'oninput="document.getElementById(\'{sid}\').textContent=this.value"></div>')

        elif t == "DateTimeInput":
            lbl = self.e(c.get("label","Date"))
            ed  = c.get("enableDate", True)
            et  = c.get("enableTime", False)
            it  = "datetime-local" if (ed and et) else ("time" if et else "date")
            return (f'<div class="flex flex-col gap-1">'
                    f'<label class="text-xs font-medium s-text-secondary">{lbl}</label>'
                    f'<input type="{it}" class="border rounded-lg px-3 py-2 text-sm"></div>')

        elif t == "RadioGroup":
            lbl  = self.e(c.get("label", ""))
            opts = c.get("options", [])
            nm   = f"rg_{cid.replace('-','_')}"
            rows = "".join(
                f'<label class="flex items-center gap-2 text-sm s-text-primary">'
                f'<input type="radio" name="{nm}" value="{self.e(o.get("value",""))}" class="w-4 h-4">'
                f'{self.e(o.get("label",""))}</label>'
                for o in opts
            )
            return f'<div class="flex flex-col gap-2"><span class="text-xs font-medium s-text-secondary">{lbl}</span>{rows}</div>'

        elif t == "Dropdown":
            lbl  = self.e(c.get("label", ""))
            opts = c.get("options", [])
            options_html = "".join(
                f'<option value="{self.e(o.get("value",""))}">{self.e(o.get("label",""))}</option>'
                for o in opts
            )
            return (f'<div class="flex flex-col gap-1">'
                    f'<label class="text-xs font-medium s-text-secondary">{lbl}</label>'
                    f'<select class="border rounded-lg px-3 py-2 text-sm">{options_html}</select></div>')

        elif t == "ChoicePicker":
            lbl  = self.e(c.get("label", ""))
            opts = c.get("options", [])
            v    = c.get("variant", "mutuallyExclusive")
            it   = "radio" if v == "mutuallyExclusive" else "checkbox"
            nm   = f"cp_{cid.replace('-','_')}"
            rows = "".join(
                f'<label class="flex items-center gap-2 text-sm s-text-primary">'
                f'<input type="{it}" name="{nm}" value="{self.e(o.get("value",""))}" class="w-4 h-4">'
                f'{self.e(o.get("label",""))}</label>'
                for o in opts
            )
            return f'<div class="flex flex-col gap-2"><span class="text-xs font-medium s-text-secondary">{lbl}</span>{rows}</div>'

        elif t == "Tabs":
            tabs = c.get("tabs", [])
            tid  = f"t_{cid.replace('-','_')}"
            btns = ""
            for i, tb in enumerate(tabs):
                active_style = f'style="background:{self.accent};color:#fff"' if i == 0 else ""
                btns += (f'<button onclick="showTab(\'{tid}\',{i})" id="{tid}_b_{i}" '
                         f'class="px-3 py-1.5 text-xs font-medium rounded-full" {active_style}>'
                         f'{self.e(tb.get("title",""))}</button>')
            panels = "".join(
                f'<div id="{tid}_p_{i}" class="{"" if i==0 else "hidden "}mt-3">{self.r(tb.get("child",""),d+1)}</div>'
                for i, tb in enumerate(tabs)
            )
            return f'<div><div class="flex gap-2 flex-wrap mb-1">{btns}</div>{panels}</div>'

        elif t == "AudioPlayer":
            url  = c.get("url", "")
            desc = self.e(c.get("description", "Audio"))
            return (f'<div class="flex flex-col gap-2">'
                    f'<p class="text-sm font-medium s-text-primary">{desc}</p>'
                    f'<audio controls src="{url}" class="w-full"></audio></div>')

        elif t == "Video":
            return f'<video controls src="{c.get("url","")}" class="w-full rounded-lg" style="max-height:220px"></video>'

        elif t == "Modal":
            trig = self.r(c.get("trigger",""),d+1)
            cont = self.r(c.get("content",""),d+1)
            mid  = f"m_{cid.replace('-','_')}"
            return (f'<div><div onclick="document.getElementById(\'{mid}\').classList.remove(\'hidden\')" '
                    f'class="cursor-pointer">{trig}</div>'
                    f'<div id="{mid}" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" '
                    f'onclick="this.classList.add(\'hidden\')"><div class="bg-white rounded-xl p-5 max-w-sm w-full mx-4" '
                    f'onclick="event.stopPropagation()">{cont}'
                    f'<button onclick="document.getElementById(\'{mid}\').classList.add(\'hidden\')" '
                    f'class="mt-3 text-xs text-gray-500">Close</button></div></div></div>')

        elif t == "Drawer":
            trig = self.r(c.get("trigger",""),d+1)
            cont = self.r(c.get("content",""),d+1)
            did  = f"d_{cid.replace('-','_')}"
            return (f'<div><div onclick="document.getElementById(\'{did}\').classList.toggle(\'hidden\')" '
                    f'class="cursor-pointer">{trig}</div>'
                    f'<div id="{did}" class="hidden mt-2 s-card">{cont}</div></div>')

        elif t in ("Carousel", "Gallery"):
            cid_s   = cid.replace("-","_")
            children = c.get("children", [])
            items_html = ""
            for idx, child_id in enumerate(children):
                disp = "block" if idx == 0 else "none"
                items_html += f'<div id="{cid_s}_s_{idx}" style="display:{disp};width:100%">{self.r(child_id,d+1)}</div>'
            total_s = len(children)
            nav = ""
            if total_s > 1:
                dots = "".join(
                    f'<button onclick="showSlide(\'{cid_s}\',{i},{total_s})" id="{cid_s}_dot_{i}" '
                    f'class="w-2 h-2 rounded-full {"bg-blue-500" if i==0 else "bg-gray-300"}"></button>'
                    for i in range(total_s)
                )
                nav = (f'<div class="flex justify-center items-center gap-2 mt-2">'
                       f'<button onclick="showSlide(\'{cid_s}\',-1,{total_s})" class="text-gray-400">‹</button>'
                       f'{dots}'
                       f'<button onclick="showSlide(\'{cid_s}\',-2,{total_s})" class="text-gray-400">›</button>'
                       f'</div>')
            return f'<div><div style="overflow:hidden">{items_html}</div>{nav}</div>'

        elif t == "Table":
            rows = "".join(self.r(x, d+1) for x in c.get("children", []))
            return f'<div class="overflow-x-auto rounded-lg border" style="border-color:{self.tokens.get("surface","#E2E8F0")}"><table class="w-full text-xs">{rows}</table></div>'

        elif t == "TableRow":
            cells = "".join(self.r(x, d+1) for x in c.get("children", []))
            if c.get("isHeader"):
                return f'<thead><tr class="font-semibold s-text-secondary" style="background:{self.tokens.get("surface","#F8FAFC")}">{cells}</tr></thead>'
            return f'<tr class="border-t s-divider">{cells}</tr>'

        elif t == "TableCell":
            ch = self.r(c.get("child",""),d+1)
            return f'<td class="px-3 py-2">{ch}</td>'

        elif t == "List":
            items = "".join(f'<li>{self.r(x,d+1)}</li>' for x in c.get("children",[]))
            return f'<ul class="flex flex-col gap-2">{items}</ul>'

        elif t in ("Stack","Grid"):
            ch   = "\n".join(self.r(x,d+1) for x in c.get("children",[]))
            cols = c.get("columns",2) if t == "Grid" else 1
            cls  = f"grid grid-cols-{min(cols,2)} gap-3" if t == "Grid" else "flex flex-col gap-3"
            return f'<div class="{cls}">{ch}</div>'

        elif t == "Loader":
            return ('<div class="flex items-center gap-2 s-text-secondary">'
                    '<div class="animate-spin w-4 h-4 border-2 border-gray-300 rounded-full" '
                    f'style="border-top-color:{self.accent}"></div>'
                    '<span class="text-xs">Loading...</span></div>')

        elif t == "Skeleton":
            return '<div class="animate-pulse rounded-lg h-12 w-full" style="background:#E2E8F0"></div>'

        elif t in ("Toast","Snackbar"):
            msg = self.e(c.get("message", c.get("text","")))
            return (f'<div class="flex items-center gap-2 px-4 py-3 rounded-lg text-sm text-white shadow-lg" '
                    f'style="background:{self.tokens.get("text_primary","#1E293B")}">'
                    f'<span>ℹ️</span><span>{msg}</span></div>')

        elif t == "FloatingActionButton":
            ch  = self.r(c.get("child",""),d+1)
            url = c.get("action",{}).get("functionCall",{}).get("args",{}).get("url","#")
            return (f'<a href="{url}" target="_blank" '
                    f'class="inline-flex items-center justify-center w-12 h-12 rounded-full '
                    f'text-white shadow-xl text-xl" style="background:{self.accent}">{ch}</a>')

        elif t == "Tooltip":
            ch  = self.r(c.get("child",""),d+1)
            tip = self.e(c.get("text",""))
            return (f'<div class="relative group cursor-pointer">{ch}'
                    f'<div class="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 '
                    f'bg-gray-800 text-white text-xs px-2 py-1 rounded opacity-0 '
                    f'group-hover:opacity-100 whitespace-nowrap z-20">{tip}</div></div>')

        elif t == "Breadcrumb":
            items = c.get("items",[])
            parts = " › ".join(
                f'<a href="{self.e(item.get("url","#"))}" class="hover:underline">'
                f'{self.e(item.get("label",""))}</a>'
                for item in items
            )
            return f'<nav class="text-xs s-text-secondary mb-2">{parts}</nav>'

        elif t in ("RefreshControl","PullToRefresh","InfiniteScroll"):
            return ""

        return f'<!-- unknown:{t} -->'

    def e(self, s):
        return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')


def build_html(query: str, a2ui: list, category: str, style_name: str = "minimal") -> str:
    primary = "#2563EB"
    comps   = []
    for msg in a2ui:
        if "createSurface" in msg:
            primary = msg["createSurface"].get("theme", {}).get("primaryColor", primary)
        if "updateComponents" in msg:
            comps = msg["updateComponents"].get("components", [])

    tokens    = STYLE_TOKENS.get(style_name, STYLE_TOKENS["minimal"])
    style_css = STYLE_CSS.get(style_name, STYLE_CSS["minimal"])
    renderer  = Renderer(comps, primary, style_name)
    body      = renderer.r("root")
    title     = renderer.e(query[:80])
    cat_label = category.replace("_"," ").title()
    bg        = tokens.get("bg","#FFFFFF")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<style>
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#E5E7EB; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; min-height:100vh; display:flex; align-items:flex-start; justify-content:center; padding:24px 16px; }}
  .device-frame {{ width:390px; min-height:844px; background:{bg}; border-radius:44px; overflow:hidden; box-shadow:0 24px 60px rgba(0,0,0,0.3), 0 0 0 10px #1a1a1a, inset 0 0 0 2px #333; position:relative; display:flex; flex-direction:column; }}
  .device-screen {{ flex:1; overflow-y:auto; overflow-x:hidden; position:relative; scrollbar-width:none; }}
  .device-screen::-webkit-scrollbar {{ display:none; }}
  .screen-content {{ padding:0 0 80px 0; }}
  .cat-pill {{ position:absolute; top:12px; right:16px; z-index:20; background:rgba(255,255,255,0.15); backdrop-filter:blur(4px); border-radius:12px; padding:4px 10px; font-size:10px; font-weight:600; letter-spacing:0.05em; color:#fff; }}
  {style_css}
  /* Override Tailwind for style classes */
  .s-card {{ margin-bottom: 0; }}
</style>
</head>
<body>
<div class="device-frame">
  <div class="device-screen">
    <div class="screen-content phone-wrap">
      {body}
    </div>
  </div>
</div>
<script>{TABS_JS}</script>
</body>
</html>"""


def process_category(category: str, dry_run: bool = False) -> int:
    a_path = os.path.join(A2UI_JSON_DIR, f"{category}.json")
    h_dir  = os.path.join(HTML_DIR, category)

    if not os.path.exists(a_path):
        print(f"  [{category}] No a2ui_json — run stage3 first")
        return 0

    with open(a_path) as f:
        data = json.load(f)

    style_name = data.get("style", CATEGORY_STYLES.get(category, "minimal"))
    valid = [r for r in data.get("results",[]) if r.get("validation",{}).get("valid") and r.get("a2ui_json")]

    os.makedirs(h_dir, exist_ok=True)
    existing = set(f for f in os.listdir(h_dir) if f.endswith(".html"))
    to_do    = [(i, r) for i, r in enumerate(valid) if f"{i:03d}.html" not in existing]

    print(f"  {category:<25} style={style_name:<8} valid={len(valid)} existing={len(existing)} to_gen={len(to_do)}")

    if dry_run or not to_do:
        return len(existing)

    done = 0
    for i, result in to_do:
        try:
            result_style = result.get("style", style_name)
            html = build_html(result["query"], result["a2ui_json"], category, result_style)
            with open(os.path.join(h_dir, f"{i:03d}.html"), "w", encoding="utf-8") as f:
                f.write(html)
            done += 1
        except Exception as e:
            print(f"    [{i}] FAILED: {e}")

    return done + len(existing)


def main():
    parser = argparse.ArgumentParser(description="Stage 4: A2UI JSON → Mobile HTML")
    parser.add_argument("--category", help="Single category to render")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cats = [args.category] if args.category else list(CATEGORIES.keys())
    print(f"\n{'='*55}\nStage 4 — Mobile HTML Generation\n{'='*55}")
    total = sum(process_category(c, args.dry_run) for c in cats)
    print(f"\nTotal HTML files: {total}")


if __name__ == "__main__":
    main()