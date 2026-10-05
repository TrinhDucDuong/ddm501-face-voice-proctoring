"""Render the reference-style architecture as a 4K PNG and editable SVG.

Run with the project's Python environment; only Pillow is required.
Coordinates are shared by both renderers so labels and connectors stay aligned.
"""

from html import escape
from pathlib import Path
import math

from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parent
W, H, SCALE = 1920, 1280, 2
BLUE, ORANGE, GREEN, RED = '#0864c9', '#d65a08', '#087851', '#d73337'
INK, MUTED = '#12304b', '#526c82'
im = Image.new('RGB', (W * SCALE, H * SCALE), '#ffffff')
d = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
       '<title id="title">DDM501 Face and Voice Integrity - System Architecture</title>',
       '<desc id="desc">Three lanes: training and data platform; CI/CD deployment and batch verification; monitoring, guarded policy promotion and rollback. Current single-host Docker Compose implementation.</desc>',
       '<rect width="1920" height="1280" fill="white"/>']
fonts = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in fonts:
        fonts[key] = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf', round(size * SCALE))
    return fonts[key]


def rect(x, y, w, h, fill, stroke=None, radius=9, width=1.3):
    d.rounded_rectangle((x*SCALE, y*SCALE, (x+w)*SCALE, (y+h)*SCALE), radius=radius*SCALE,
                        fill=fill, outline=stroke, width=max(1, round(width*SCALE)))
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')


def ellipse(x, y, w, h, fill, stroke=None, width=1.5):
    d.ellipse((x*SCALE, y*SCALE, (x+w)*SCALE, (y+h)*SCALE), fill=fill, outline=stroke, width=round(width*SCALE))
    svg.append(f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{width}"/>')


def poly(points, fill, stroke=None, width=1.5):
    scaled = [(x*SCALE, y*SCALE) for x, y in points]
    d.polygon(scaled, fill=fill)
    if stroke:
        d.line(scaled+[scaled[0]], fill=stroke, width=round(width*SCALE), joint='curve')
    svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in points)}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')


def line(points, color=BLUE, width=2, arrow=False, dashed=False):
    scaled = [(x*SCALE, y*SCALE) for x, y in points]
    if dashed:
        for (ax, ay), (bx, by) in zip(scaled, scaled[1:]):
            length = math.hypot(bx-ax, by-ay)
            for start in range(0, round(length), 12*SCALE):
                end = min(start+7*SCALE, length)
                d.line((ax+(bx-ax)*start/length, ay+(by-ay)*start/length,
                        ax+(bx-ax)*end/length, ay+(by-ay)*end/length), fill=color, width=round(width*SCALE))
    else:
        d.line(scaled, fill=color, width=round(width*SCALE), joint='curve')
    dash = ' stroke-dasharray="7 5"' if dashed else ''
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{dash}/>')
    if arrow:
        ax, ay = points[-2]
        bx, by = points[-1]
        angle = math.atan2(by-ay, bx-ax)
        poly([(bx, by), (bx-9*math.cos(angle)+4.5*math.sin(angle), by-9*math.sin(angle)-4.5*math.cos(angle)),
              (bx-9*math.cos(angle)-4.5*math.sin(angle), by-9*math.sin(angle)+4.5*math.cos(angle))], color)


def text(x, y, value, size=17, bold=False, color=INK, anchor='start', max_width=None):
    f = font(size, bold)
    tw = d.textlength(value, font=f)/SCALE
    if max_width is not None:
        assert tw <= max_width, f'Text exceeds box: {value}: {tw:.1f} > {max_width}'
    px = x - (tw/2 if anchor == 'middle' else tw if anchor == 'end' else 0)
    assert px >= 0 and px+tw <= W, value
    d.text((px*SCALE, y*SCALE), value, font=f, fill=color, anchor='lt')
    svg.append(f'<text x="{x}" y="{y+size*.81}" font-family="Segoe UI, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}" text-anchor="{anchor}">{escape(value)}</text>')


def icon(kind, x, y, color=BLUE):
    # Compact vector symbols, intentionally independent of external icon fonts.
    def ln(p, width=2):
        line([(x+a, y+b) for a,b in p], color, width)
    if kind == 'db':
        rect(x+3,y+7,26,23,color,radius=0)
        ellipse(x+3,y+24,26,10,color)
        ellipse(x+3,y+2,26,10,color)
        ln([(4,16),(10,19),(22,19),(28,16)],1)
        line([(x+5,y+14),(x+12,y+17),(x+21,y+17),(x+27,y+14)],'#ffffff',1)
        line([(x+5,y+23),(x+12,y+26),(x+21,y+26),(x+27,y+23)],'#ffffff',1)
    elif kind == 'person':
        ellipse(x+10,y+2,12,12,None,color,2)
        ln([(4,31),(5,25),(10,20),(22,20),(27,25),(28,31)])
        ln([(1,10),(1,1),(8,1)])
        ln([(24,1),(31,1),(31,10)])
    elif kind == 'shield':
        poly([(x+16,y+1),(x+29,y+6),(x+27,y+23),(x+16,y+33),(x+5,y+23),(x+3,y+6)],'#ffffff',color,2)
        ln([(9,16),(14,21),(23,11)],2.7)
    elif kind == 'git':
        ln([(8,6),(8,27),(24,27),(24,10)])
        ln([(8,9),(24,21)])
        for a,b in [(8,5),(8,28),(24,8)]:
            ellipse(x+a-4,y+b-4,8,8,'#ffffff',color,2)
    elif kind == 'chart':
        ln([(2,2),(2,31),(31,31)])
        for a,b in [(8,16),(17,10),(26,3)]:
            rect(x+a,y+b,5,27-b,color,radius=1)
    elif kind == 'flow':
        ln([(16,9),(16,18),(5,18),(5,24)])
        ln([(16,18),(27,18),(27,24)])
        for a,b in [(11,0),(0,24),(22,24)]:
            rect(x+a,y+b,10,9,'#ffffff',color,2)
    elif kind == 'cube':
        poly([(x+16,y+1),(x+30,y+9),(x+30,y+25),(x+16,y+33),(x+2,y+25),(x+2,y+9)],'#ffffff',color,2)
        ln([(2,9),(16,17),(30,9)])
        ln([(16,17),(16,33)])
        ln([(9,5),(23,13)])
    elif kind == 'server':
        for b in (2,20):
            rect(x+1,y+b,30,13,color,radius=3)
            ellipse(x+5,y+b+4,4,4,'#ffffff')
            line([(x+14,y+b+6),(x+26,y+b+6)],'#ffffff',2)
    elif kind == 'check':
        ellipse(x+1,y+1,31,31,color)
        line([(x+8,y+16),(x+14,y+22),(x+25,y+10)],'#ffffff',3)
    elif kind == 'bell':
        poly([(x+4,y+26),(x+7,y+21),(x+7,y+12),(x+11,y+6),(x+21,y+6),(x+25,y+12),(x+25,y+21),(x+28,y+26)],color)
        ellipse(x+13,y+28,7,5,color)
        ellipse(x+14,y+2,5,5,color)
    elif kind == 'loop':
        ln([(27,10),(24,5),(15,2),(7,6),(3,14),(5,24),(14,30),(23,29),(29,23)],2.5)
        poly([(x+21,y+11),(x+29,y+13),(x+30,y+4)],color)
    else:
        rect(x+5,y+1,23,32,'#ffffff',color,3,2)
        for b in (10,17,24):
            ln([(10,b),(22,b)])


def box(x,y,w,h,title,sub=(),kind=None,color=BLUE,fill='#ffffff',title_size=18,sub_size=15):
    rect(x,y+2,w,h,'#dce5ed',radius=8)
    rect(x,y,w,h,fill,color,8,1.2)
    if kind:
        icon(kind,x+14,y+(h-34)/2,color)
    tx = x+60 if kind else x+15
    title_lines = title if isinstance(title,list) else [title]
    sub_lines = [sub] if isinstance(sub,str) else list(sub)
    available = x+w-tx-12
    while max(d.textlength(v,font=font(title_size,True))/SCALE for v in title_lines) > available and title_size > 13:
        title_size -= 1
    while sub_lines and max(d.textlength(v,font=font(sub_size))/SCALE for v in sub_lines) > available and sub_size > 12:
        sub_size -= 1
    block_h = len(title_lines)*(title_size+4)+len(sub_lines)*(sub_size+4)-4
    ty = y+(h-block_h)/2
    for value in title_lines:
        text(tx,ty,value,title_size,True,max_width=x+w-tx-12)
        ty += title_size+4
    for value in sub_lines:
        text(tx,ty,value,sub_size,color=MUTED,max_width=x+w-tx-12)
        ty += sub_size+4


def lane(y,h,n,title,subtitle,color,tint,note):
    rect(14,y,1892,h,tint,color,12,1.5)
    rect(14,y,1892,43,color,radius=11)
    rect(14,y+25,1892,18,color,radius=0)
    ellipse(33,y+6,31,31,'#ffffff')
    text(48.5,y+7,str(n),25,True,color,anchor='middle')
    text(81,y+9,title,24,True,'#ffffff')
    text(subtitle[0],y+13,subtitle[1],17,color='#ffffff')
    text(1887,y+14,note,15,color='#ffffff',anchor='end')


text(25,16,'DDM501  |  FACE & VOICE INTEGRITY',29,True)
text(27,53,'System architecture  /  Company batch verification + guarded MLOps lifecycle',17,color=MUTED)
rect(1450,22,444,35,'#edf4fb','#c4d8e8',17)
text(1672,30,'SINGLE HOST  /  DOCKER COMPOSE',16,True,BLUE,'middle')

lane(85,333,1,'Training and data platform',(444,'Code delivery + model development'),BLUE,'#edf6ff','Face and Voice: independent threshold policies')
box(39,146,183,63,'GitHub push','main / develop','git')
box(250,146,260,63,'GitHub Actions',['Ubuntu quality','Windows preflight'],'flow',title_size=18,sub_size=13)
box(538,146,225,63,'Container builds','Docker Compose','cube')
box(791,146,324,63,'Self-hosted Linux / WSL','Trusted main deployment','server')
box(1143,146,737,63,'Docker Desktop / Compose runtime','FastAPI | Streamlit | Airflow | MLflow | storage | monitoring','server')
for a,b in [(222,250),(510,538),(763,791),(1115,1143)]:
    line([(a,177),(b,177)],arrow=True)
text(40,224,'Airflow training DAG',18,True)
text(273,226,'On demand  |  biometric_model_pipeline  |  training tenant: demo',15,color=MUTED)
steps = [
    ('1  Freeze snapshot',['Versioned observations','Fingerprint + trusted labels'],'doc'),
    ('2  Validate data',['Data quality gate','Identity / sample checks'],'shield'),
    ('3  Publish dataset',['MinIO manifest + splits','Versioned training data'],'cube'),
    ('4  Calibrate thresholds',['Identity-disjoint CV','Register MLflow candidate'],'chart'),
    ('5  Responsible AI',['Generate audit report','Human / synthetic separate'],'doc'),
    ('6  Offline gate',['Paired champion evaluation','Reserved holdout'],'shield'),
    ('7  Lifecycle tick',['Persist state + audit','Enter guarded rollout (3)'],'flow'),
]
for i,(title,sub,kind) in enumerate(steps):
    x=39+i*266
    box(x,256,245,79,title,sub,kind,title_size=16,sub_size=13)
    if i<6:
        line([(x+245,295),(x+266,295)],arrow=True)
box(39,357,510,43,'MinIO', 'Datasets, manifests, MLflow artifacts',kind='cube',title_size=16,sub_size=13)
box(574,357,735,43,'MLflow Registry', 'face-verification / voice-verification; champion, challenger, previous_champion',kind='db',title_size=16,sub_size=13)
box(1334,357,546,43,'PostgreSQL', 'MLflow metadata + deployment state + audit',kind='db',title_size=16,sub_size=13)
line([(671,335),(671,346),(293,346),(293,357)],arrow=True,width=1.5)
line([(960,335),(960,357)],arrow=True,width=1.5)
line([(1758,335),(1758,346),(1607,346),(1607,357)],arrow=True,width=1.5)

lane(431,352,2,'Serving and customer integration',(542,'Identity + capture integrity'),ORANGE,'#fff6ed','Company owns exams, capture timing and business decisions')
box(39,501,235,88,'Company backend',['Employee + session IDs','Consent + image / WAV'],'server',ORANGE,title_size=17,sub_size=14)
box(39,625,235,77,'Streamlit portal',['Enrollment, keys, history','Evidence + PDF / CSV'],'person',ORANGE,title_size=17,sub_size=13)
box(316,525,245,123,'FastAPI',['POST /v1/checks','Tenant API key','Validation + idempotency'],'server',ORANGE,title_size=23,sub_size=15)
line([(274,545),(295,545),(295,555),(316,555)],ORANGE,arrow=True)
line([(274,663),(296,663),(296,619),(316,619)],ORANGE,arrow=True)
box(607,501,363,88,'1:1 identity verification',['YuNet / SFace + ECAPA embeddings','Face / Voice policy thresholds'],'person',BLUE,title_size=18,sub_size=14)
box(607,620,363,82,'Capture integrity inspectors',['Face count + MiniFASNet PAD + AASIST','Speaker consistency + media reuse'],'shield',BLUE,title_size=18,sub_size=13)
line([(561,583),(586,583),(586,545),(607,545)],arrow=True)
line([(586,583),(586,661),(607,661)],arrow=True)
box(1015,548,237,104,'Check result',['Verified / Suspicious','/ Inconclusive','Scores + reasons + limits'],'check',ORANGE,title_size=19,sub_size=14)
line([(970,545),(992,545),(992,578),(1015,578)],arrow=True)
line([(970,661),(992,661),(992,623),(1015,623)],arrow=True)
box(1298,501,261,95,'PostgreSQL',['Employees / templates','Checks + events + outbox','Atomic metadata commit'],'db',BLUE,title_size=19,sub_size=13)
box(1298,630,261,72,'MinIO evidence',['Suspicious media only','Tenant / check scoped'],'cube',BLUE,title_size=18,sub_size=13)
line([(1252,582),(1276,582),(1276,548),(1298,548)],arrow=True)
line([(1252,616),(1276,616),(1276,666),(1298,666)],arrow=True)
box(1604,501,276,95,'Webhook worker',['Durable outbox delivery','HMAC signatures + retries','Customer deduplicates'],'flow',ORANGE,title_size=19,sub_size=14)
line([(1559,548),(1604,548)],ORANGE,arrow=True)
box(1604,630,276,72,'Signed callback',['Same immutable result','To the company backend'],'doc',ORANGE,title_size=18,sub_size=13)
line([(1742,596),(1742,630)],ORANGE,arrow=True)
line([(1133,652),(1133,727),(287,727),(287,574),(274,574)],ORANGE,arrow=True)
rect(387,715,383,25,'#fff6ed',radius=3)
text(400,719,'Immediate JSON result to company backend',15,True,ORANGE)
line([(1742,702),(1742,727),(1147,727)],ORANGE,arrow=True,dashed=True)
rect(1340,714,306,25,'#fff6ed',radius=3)
text(1352,719,'Async callback to the same backend',14,True,ORANGE)
text(41,753,'PRETRAINED ENCODERS  |  One API process  |  Canary selects threshold policy inside FastAPI  |  Ordinary raw captures discarded by default',16,True,color=MUTED)

lane(796,412,3,'Monitoring and decision loop',(484,'Drift, trusted evidence and guarded rollout'),GREEN,'#edf9f3','Promote, preserve champion or restore a previous version')
box(39,861,237,87,'PostgreSQL evidence',['Checks + observations','Trusted review labels'],'db',GREEN,title_size=17,sub_size=14)
box(305,861,274,87,'Airflow hourly monitoring',['Reference vs. current windows','Per-modality decisions'],'flow',GREEN,title_size=17,sub_size=14)
box(608,861,390,87,'Drift + reviewed performance',['Quality PSI / embedding MMD / score PSI','FMR / FNMR + template-age cohorts'],'chart',GREEN,title_size=17,sub_size=13)
line([(276,904),(305,904)],GREEN,arrow=True)
line([(579,904),(608,904)],GREEN,arrow=True)
line([(804,948),(804,970),(171,970),(171,990)],GREEN,arrow=True)
line([(804,970),(501,970),(501,990)],GREEN,arrow=True)
line([(804,970),(846,970),(846,990)],GREEN,arrow=True)
box(39,990,264,78,'Monitor / wait',['Healthy, quality drift or','insufficient trusted evidence'],'chart',GREEN,fill='#f8fcfa',title_size=17,sub_size=14)
box(331,990,339,78,'Trusted template update',['Old-template-only degradation','Versioned + holdout + operator rollback'],'person',GREEN,fill='#e3f5ed',title_size=17,sub_size=13)
box(698,990,300,78,'Request retraining',['Persistent drift + reviewed degradation','To training DAG (1); cooldown gate'],'loop',BLUE,fill='#eaf4ff',title_size=17,sub_size=12)
text(40,1085,'PLATFORM OBSERVABILITY',14,True,GREEN)
box(39,1111,208,62,'Evidently / PSI',['60-second reports','Operational drift'],'chart',BLUE,title_size=15,sub_size=12)
box(269,1111,242,62,'Prometheus / Grafana',['Metrics + dashboards','SQL + Loki / Alloy logs'],'chart',BLUE,title_size=15,sub_size=12)
box(533,1111,223,62,'Alertmanager',['Alert routing','Production notifications'],'bell',RED,title_size=16,sub_size=12)
box(778,1111,220,62,'ops-monitor',['Telegram alerts','Readiness + resources'],'server',GREEN,title_size=16,sub_size=12)
for a,b in [(247,269),(511,533),(756,778)]:
    line([(a,1142),(b,1142)],BLUE,arrow=True)
text(40,1186,'Evidently reports do not trigger a second training path. Missing labels pause lifecycle progression.',13,color=MUTED)

rect(1022,851,859,334,'#f8fffb','#8cc6ab',9)
text(1041,865,'POLICY ROLLOUT  |  Separate Face / Voice state machines',18,True,GREEN)
box(1043,900,186,65,'Shadow',['Champion responds','Record both policies'],'flow',BLUE,title_size=18,sub_size=12)
box(1260,900,285,65,'Canary policy',['5 / 10 / 25 / 50 / 100%','Stable cohort hash routing'],'flow',ORANGE,fill='#fff3e5',title_size=18,sub_size=14)
line([(1229,932),(1260,932)],GREEN,arrow=True)
poly([(1647,891),(1720,932),(1647,973),(1574,932)],'#0a6699','#084b74',1.5)
text(1647,914,'Stage gates',16,True,'#ffffff','middle')
text(1647,936,'pass?',16,True,'#ffffff','middle')
line([(1545,932),(1574,932)],GREEN,arrow=True)
text(1758,907,'Samples + time',13,color=MUTED)
text(1758,928,'Labels + FMR/FNMR',12,color=MUTED)
text(1758,949,'Latency + cohorts',13,color=MUTED)
box(1043,993,375,166,'Persisted serving policy',['PostgreSQL deployment + audit','MLflow champion / challenger','Keep previous_champion version','Policy routing consumed by FastAPI (2)'],'db',BLUE,fill='#eaf4ff',title_size=19,sub_size=14)
box(1460,1008,400,65,'Promote challenger',['Final stage passes: commit new champion','Preserve the previous champion'],'check',GREEN,fill='#ddf6e6',title_size=19,sub_size=13)
box(1460,1094,400,65,'Stop rollout / rollback',['Failed gate: preserve current champion','Operator rollback: restore previous version'],'loop',RED,fill='#fff0ef',title_size=19,sub_size=13)
line([(1647,973),(1647,1008)],GREEN,arrow=True)
text(1659,983,'Yes / final',12,True,GREEN)
line([(1720,932),(1738,932),(1738,977),(1870,977),(1870,1126),(1860,1126)],RED,arrow=True)
text(1768,984,'No / regression',12,True,RED)
line([(1460,1041),(1418,1041)],GREEN,arrow=True)
line([(1460,1126),(1418,1126)],RED,arrow=True)
text(1044,1170,'Offline + shadow failures also preserve the champion. Thresholds are calibrated; encoders stay fixed.',12,color=MUTED)

rect(14,1220,1892,48,'#f0f5f9','#c5d6e3',8)
text(32,1236,'Legend:',14,True)
for x,c,label in [(99,'#ddf6e6','Champion / promotion'),(339,'#fff3e5','Challenger / canary'),(569,'#eaf4ff','Stored state / previous'),(812,'#fff0ef','Failure / rollback')]:
    rect(x,1233,23,20,c,{'#ddf6e6':GREEN,'#fff3e5':ORANGE,'#eaf4ff':BLUE,'#fff0ef':RED}[c],4)
    text(x+33,1236,label,13)
line([(1021,1230),(1021,1259)],'#bdcedc',1)
text(1042,1230,'ISOLATED SIMULATION',13,True)
text(1241,1230,'Synthetic data | SQLite + file MLflow + separate volume',13,color=MUTED)
text(1042,1250,'Promote / fail at 25% / reset; shared host + Airflow. Simulation alerts use their own receiver.',12,color=MUTED)

svg.append('</svg>')
svg_path = OUT / 'DDM501_Architecture_Reference_Style.svg'
png_path = OUT / 'DDM501_Architecture_Reference_Style.png'
svg_path.write_text('\n'.join(svg), encoding='utf-8')
im.save(png_path, dpi=(200,200), optimize=True)
im.resize((W,H), Image.Resampling.LANCZOS).save(OUT/'DDM501_Architecture_Reference_Style_preview.png')
print(f'PNG: {png_path} ({im.width} x {im.height})')
print(f'SVG: {svg_path}')
