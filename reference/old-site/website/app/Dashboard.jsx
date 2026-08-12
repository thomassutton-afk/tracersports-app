'use client'

import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import Link from "next/link";
import Footer from '../components/Footer'

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────
const TEAM_INFO = {
  ATL:{ name:'Atlanta Hawks',          conf:'East', div:'Southeast' },
  BOS:{ name:'Boston Celtics',         conf:'East', div:'Atlantic'  },
  BRK:{ name:'Brooklyn Nets',          conf:'East', div:'Atlantic'  },
  CHA:{ name:'Charlotte Hornets',      conf:'East', div:'Southeast' },
  CHI:{ name:'Chicago Bulls',          conf:'East', div:'Central'   },
  CLE:{ name:'Cleveland Cavaliers',    conf:'East', div:'Central'   },
  DAL:{ name:'Dallas Mavericks',       conf:'West', div:'Southwest' },
  DEN:{ name:'Denver Nuggets',         conf:'West', div:'Northwest' },
  DET:{ name:'Detroit Pistons',        conf:'East', div:'Central'   },
  GS: { name:'Golden State Warriors',  conf:'West', div:'Pacific'   },
  HOU:{ name:'Houston Rockets',        conf:'West', div:'Southwest' },
  IND:{ name:'Indiana Pacers',         conf:'East', div:'Central'   },
  LAC:{ name:'LA Clippers',            conf:'West', div:'Pacific'   },
  LAL:{ name:'Los Angeles Lakers',     conf:'West', div:'Pacific'   },
  MEM:{ name:'Memphis Grizzlies',      conf:'West', div:'Southwest' },
  MIA:{ name:'Miami Heat',             conf:'East', div:'Southeast' },
  MIL:{ name:'Milwaukee Bucks',        conf:'East', div:'Central'   },
  MIN:{ name:'Minnesota Timberwolves', conf:'West', div:'Northwest' },
  NO: { name:'New Orleans Pelicans',   conf:'West', div:'Southwest' },
  NY: { name:'New York Knicks',        conf:'East', div:'Atlantic'  },
  OKC:{ name:'Oklahoma City Thunder',  conf:'West', div:'Northwest' },
  ORL:{ name:'Orlando Magic',          conf:'East', div:'Southeast' },
  PHI:{ name:'Philadelphia 76ers',     conf:'East', div:'Atlantic'  },
  PHX:{ name:'Phoenix Suns',           conf:'West', div:'Pacific'   },
  POR:{ name:'Portland Trail Blazers', conf:'West', div:'Northwest' },
  SA: { name:'San Antonio Spurs',      conf:'West', div:'Southwest' },
  SAC:{ name:'Sacramento Kings',       conf:'West', div:'Pacific'   },
  TOR:{ name:'Toronto Raptors',        conf:'East', div:'Atlantic'  },
  UTA:{ name:'Utah Jazz',              conf:'West', div:'Northwest' },
  WAS:{ name:'Washington Wizards',     conf:'East', div:'Southeast' },
}

const TEAM_COLORS = {
  ATL:'#C8102E', BOS:'#007A33', BRK:'#000000', CHA:'#00778B',
  CHI:'#CE1141', CLE:'#860038', DAL:'#0050B5', DEN:'#0E2240',
  DET:'#1D42BA', GS:'#1D428A',  HOU:'#CE1141', IND:'#002D62',
  LAC:'#0C2340', LAL:'#552583', MEM:'#5D76A9', MIA:'#98002E',
  MIL:'#00471B', MIN:'#236192', NO:'#0C2340',  NY:'#1D4289',
  OKC:'#0072CE', ORL:'#0050B5', PHI:'#006BB6', PHX:'#1D1160',
  POR:'#E03A3E', SA:'#9EA2A2',  SAC:'#5A2D81', TOR:'#BA0C2F',
  UTA:'#330072', WAS:'#E31837',
}

// Secondary — left border line
const TEAM_SECONDARY = {
  ATL:'#FDB927', BOS:'#FFFFFF', BRK:'#FFFFFF', CHA:'#1D1160',
  CHI:'#000000', CLE:'#B9975B', DAL:'#B8C4CA', DEN:'#FEC524',
  DET:'#C8102E', GS:'#FFC72C',  HOU:'#000000', IND:'#FDBB30',
  LAC:'#C8102E', LAL:'#FDB927', MEM:'#F5B112', MIA:'#F9A01B',
  MIL:'#EEE1C6', MIN:'#78BE21', NO:'#B9975B',  NY:'#FF8200',
  OKC:'#F9423A', ORL:'#000000', PHI:'#ED174C', PHX:'#E56020',
  POR:'#000000', SA:'#000000',  SAC:'#FFFFFF', TOR:'#000000',
  UTA:'#FFFFFF', WAS:'#002B5C',
}

// Tertiary — accent dot / strength bar highlight
const TEAM_TERTIARY = {
  ATL:'#FFFFFF', BOS:'#BA9653', BRK:'#707372', CHA:'#FFFFFF',
  CHI:'#FFFFFF', CLE:'#000000', DAL:'#9EA2A2', DEN:'#8B2131',
  DET:'#FFFFFF', GS:'#FFFFFF',  HOU:'#C4CED4', IND:'#FFFFFF',
  LAC:'#FFFFFF', LAL:'#000000', MEM:'#12173F', MIA:'#000000',
  MIL:'#000000', MIN:'#0C2340', NO:'#C8102E',  NY:'#FFFFFF',
  OKC:'#FFB81C', ORL:'#9EA2A2', PHI:'#FFFFFF', PHX:'#FFFFFF',
  POR:'#FFFFFF', SA:'#FFFFFF',  SAC:'#707372', TOR:'#FFFFFF',
  UTA:'#000000', WAS:'#9EA2A2',
}

const tt = a => TEAM_TERTIARY[a]||'#FFFFFF'

const EAST_TEAMS = new Set(Object.entries(TEAM_INFO).filter(([,v])=>v.conf==='East').map(([k])=>k))
const WEST_TEAMS = new Set(Object.entries(TEAM_INFO).filter(([,v])=>v.conf==='West').map(([k])=>k))

const DIVISIONS = {
  East:{ Atlantic:['BOS','BRK','NY','PHI','TOR'], Central:['CHI','CLE','DET','IND','MIL'], Southeast:['ATL','CHA','MIA','ORL','WAS'] },
  West:{ Northwest:['DEN','MIN','OKC','POR','UTA'], Pacific:['GS','LAC','LAL','PHX','SAC'], Southwest:['DAL','HOU','MEM','NO','SA'] },
}

// ─────────────────────────────────────────────────────────────────────────────
// Logo path helper
// ─────────────────────────────────────────────────────────────────────────────
function getCurrentLogoPath(team_id) {
  return `/logos/current/${team_id}.png`
}

// ─────────────────────────────────────────────────────────────────────────────
// TeamLogo component
// ─────────────────────────────────────────────────────────────────────────────
function TeamLogo({ abbr, size = 28, style = {} }) {
  const [errored, setErrored] = useState(false)
  const src = getCurrentLogoPath(abbr)
  const color = TEAM_COLORS[abbr] || '#663399'

  if (errored) {
    return (
      <span style={{
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: Math.max(8, size * 0.38),
        fontWeight: 700,
        padding: '2px 6px',
        borderRadius: 4,
        border: `1.5px solid ${color}`,
        color,
        letterSpacing: 0.3,
        flexShrink: 0,
        lineHeight: 1,
        display: 'inline-flex',
        alignItems: 'center',
        ...style,
      }}>
        {abbr}
      </span>
    )
  }

  return (
    <img
      src={src}
      alt={abbr}
      width={size}
      height={size}
      onError={() => setErrored(true)}
      style={{
        width: size,
        height: size,
        objectFit: 'contain',
        flexShrink: 0,
        display: 'block',
        filter: 'drop-shadow(0 0 4px rgba(255,255,255,0.95)) drop-shadow(0 0 10px rgba(255,255,255,0.6))',
        ...style,
      }}
    />
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function formatDate(dateStr) {
  const [y,m,d] = dateStr.split('-').map(Number)
  return new Date(y,m-1,d).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})
}
function roundLabel(round,type) {
  if(type==='R') return 'Regular Season'
  return {'0.5':'Play-In',INS:'In-Season Tourn.','1':'Round 1','2':'Conf Semis','3':'Conf Finals','4':'NBA Finals'}[round]||round
}
const tc = a => TEAM_COLORS[a]||'#663399'
const ts = a => TEAM_SECONDARY[a]||TEAM_COLORS[a]||'#663399'
const tn = a => TEAM_INFO[a]?.name||a
const nick = a => tn(a).split(' ').slice(-1)[0]
const winPct = t => t.w/(t.w+t.l||1)

// Sort by win%, then by wins as tiebreak
function standingsSort(a,b) {
  const pa=winPct(a), pb=winPct(b)
  if(Math.abs(pa-pb)>0.0001) return pb-pa
  return b.w-a.w
}

// Manual seed overrides for tied teams where head-to-head or other tiebreakers
// differ from simple win%. Only applied when win% AND wins are identical.
const WEST_SEED_OVERRIDES={ POR:8, LAC:9 }
const EAST_SEED_OVERRIDES={ PHI:7, ORL:8 }

function standingsSortWithOverrides(overrides) {
  return function(a,b) {
    const pa=winPct(a), pb=winPct(b)
    if(Math.abs(pa-pb)>0.0001) return pb-pa
    if(b.w!==a.w) return b.w-a.w
    const oa=overrides[a.abbr], ob=overrides[b.abbr]
    if(oa!=null&&ob!=null) return oa-ob
    return 0
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Design tokens
// ─────────────────────────────────────────────────────────────────────────────
const mono  = "'IBM Plex Mono', monospace"
const serif = "'Playfair Display', Georgia, serif"
const C = {
  bg:'#F5F0E8', surface:'#FDFAF5', border:'#EDE8DD', border2:'#E0D9CE',
  text:'#1A1816', text2:'#5C5650', text3:'#9A9490',
  acc:'#663399', ut:'#BF5700', uo:'#154733',
}

// ─────────────────────────────────────────────────────────────────────────────
// Data fetch
// ─────────────────────────────────────────────────────────────────────────────
async function getData(variant) {
  const [{data:ratings},{data:wlData},{data:rsGames},{data:accData},{data:poGames}] = await Promise.all([
    supabase.from('current_ratings').select('team_id,post_gm_rate,rating_change').eq('variant',variant),
    supabase.from('season_records').select('team_id,wins,losses').eq('season',2026).eq('variant',variant),
    supabase.from('games').select('team_id,post_gm_rate,date').eq('season',2026).eq('variant',variant).eq('type','R').order('date',{ascending:false}),
    supabase.from('season_accuracy').select('game_count,avg_accuracy,avg_brier').eq('season',2026).eq('variant',variant).single(),
    supabase.from('games').select('team_id,round,result,post_gm_rate,opponent_id,home_away,points_for,points_against,date,game_id').eq('season',2026).eq('variant',variant).eq('type','P').not('round','in','("INS")').order('date',{ascending:true}),
  ])

  const wlMap={}, rsMap={}
  for(const r of wlData||[]) wlMap[r.team_id]={w:r.wins,l:r.losses}
  for(const g of rsGames||[]) if(!rsMap[g.team_id]) rsMap[g.team_id]=g.post_gm_rate

  const teams=(ratings||[]).map(t=>({
    abbr:t.team_id, rating:t.post_gm_rate, rsRating:rsMap[t.team_id]??t.post_gm_rate,
    change:t.rating_change, w:wlMap[t.team_id]?.w||0, l:wlMap[t.team_id]?.l||0,
    ...(TEAM_INFO[t.team_id]||{name:t.team_id,conf:'?',div:'?'}),
  })).sort((a,b)=>b.rating-a.rating)

  const accuracy=accData?{
    pct:(accData.avg_accuracy*100).toFixed(1),
    brier:Number(accData.avg_brier).toFixed(3),
    n:Number(accData.game_count).toLocaleString(),
  }:null

  return {teams,accuracy,poGames:poGames||[]}
}

// ─────────────────────────────────────────────────────────────────────────────
// Games-by-date fetch — powers the Recent Games sidebar's date picker.
// Pulls every completed game on the given date and pairs home/away rows.
// ─────────────────────────────────────────────────────────────────────────────
function pairGameRows(rows) {
  const seen=new Set(), games=[]
  for(const row of rows) {
    if(row.home_away!=='H'||!row.points_for||row.points_for<50) continue
    const key=`${row.date}_${row.team_id}_${row.opponent_id}`
    if(seen.has(key)) continue; seen.add(key)
    const aw=rows.find(g=>g.date===row.date&&g.team_id===row.opponent_id&&g.home_away==='A')
    games.push({date:row.date,home:row.team_id,away:row.opponent_id,
      homeScore:row.points_for,awayScore:row.points_against,
      homeRating:row.post_gm_rate,awayRating:aw?.post_gm_rate??null,
      homeChange:row.rating_change,awayChange:aw?.rating_change??null,
      winProb:row.expected_win_pct,round:row.round,type:row.type,ot:row.ot||false})
  }
  return games
}

async function getGamesForDate(dateStr,variant) {
  const {data:rows}=await supabase.from('games')
    .select('team_id,post_gm_rate,rating_change,date,type,round,opponent_id,home_away,points_for,points_against,expected_win_pct,ot')
    .eq('season',2026).eq('variant',variant).eq('date',dateStr)
  return pairGameRows(rows||[])
}

async function getLatestGameDate(variant) {
  const {data}=await supabase.from('games').select('date')
    .eq('season',2026).eq('variant',variant).eq('home_away','H')
    .not('points_for','is',null).order('date',{ascending:false}).limit(1)
  return data?.[0]?.date ?? null
}

function shiftDate(dateStr,delta) {
  const [y,m,d]=dateStr.split('-').map(Number)
  const dt=new Date(y,m-1,d)
  dt.setDate(dt.getDate()+delta)
  return `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')}`
}

// ─────────────────────────────────────────────────────────────────────────────
// Bracket builder
// ─────────────────────────────────────────────────────────────────────────────
function buildBracket(poGames) {
  const map={}
  for(const g of poGames) {
    const pair=[g.team_id,g.opponent_id].sort().join('_')
    const key=`${g.round}_${pair}`
    if(!map[key]){
      const [a,b]=[g.team_id,g.opponent_id].sort()
      map[key]={round:g.round,t1:a,t2:b,wins:{[a]:0,[b]:0},latestRating:{},latestDate:'',games:[]}
    }
    const s=map[key]
    s.games.push(g)
    if(g.result===1) s.wins[g.team_id]=(s.wins[g.team_id]||0)+1
    if(g.date>=s.latestDate){s.latestDate=g.date;s.latestRating[g.team_id]=g.post_gm_rate}
  }
  return Object.values(map).map(s=>{
    const{t1,t2}=s,w1=s.wins[t1]||0,w2=s.wins[t2]||0
    const maxWins=s.round==='0.5'?1:4
    const winner=w1>=maxWins?t1:w2>=maxWins?t2:null
    const loser=winner?(winner===t1?t2:t1):null
    return{...s,w1,w2,winner,loser,maxWins}
  })
}

// ─────────────────────────────────────────────────────────────────────────────
// StandingsTab — symmetric side-by-side, sorted by win%, grouped
// ─────────────────────────────────────────────────────────────────────────────
function StandingsTab({teams,poGames}) {
  const [view,setView]=useState('conference')

  // Playoff records
  const poRec={}
  for(const g of poGames){
    if(!poRec[g.team_id]) poRec[g.team_id]={r1w:0,r1l:0,r2w:0,r2l:0,r3w:0,r3l:0,fw:0,fl:0,piw:0,pil:0}
    const r=poRec[g.team_id],rnd=parseFloat(g.round),win=g.result===1
    if(rnd===0.5){win?r.piw++:r.pil++}
    if(rnd===1){win?r.r1w++:r.r1l++}
    if(rnd===2){win?r.r2w++:r.r2l++}
    if(rnd===3){win?r.r3w++:r.r3l++}
    if(rnd===4){win?r.fw++:r.fl++}
  }

  function PlayoffBadge({abbr}) {
    const r=poRec[abbr]
    if(!r) return <span style={{color:C.text3,fontFamily:mono,fontSize:11}}>—</span>
    const s=(col,fw)=>({color:col,fontFamily:mono,fontSize:11,fontWeight:fw||400})
    if(r.fw>=4)           return <span style={s(C.ut,700)}>🏆 Champion</span>
    if(r.fw>0||r.fl>0)   return <span style={s('#444',500)}>Finals ({r.fw}–{r.fl})</span>
    if(r.r3w>0||r.r3l>0) return <span style={s('#555')}>CF ({r.r3w}–{r.r3l})</span>
    if(r.r2w>0||r.r2l>0) return <span style={s('#666')}>CS ({r.r2w}–{r.r2l})</span>
    if(r.r1w>0||r.r1l>0) return <span style={s('#888')}>R1 ({r.r1w}–{r.r1l})</span>
    if(r.piw>0||r.pil>0) return <span style={s('#aaa')}>Play-In</span>
    return <span style={{color:C.text3,fontFamily:mono,fontSize:11}}>—</span>
  }

  const teamMap={}; for(const t of teams) teamMap[t.abbr]=t
  const maxRS=Math.max(...teams.map(t=>t.rsRating||0))
  const minRS=Math.min(...teams.map(t=>t.rsRating||9999))

  const TH=({label,align='right'})=>(
    <th style={{fontFamily:mono,fontSize:9,fontWeight:500,color:C.text3,textTransform:'uppercase',
      letterSpacing:1.2,padding:'7px 8px',textAlign:align,whiteSpace:'nowrap',
      background:'#fff',borderBottom:`2px solid ${C.border}`}}>{label}</th>
  )

  function TeamRow({t,seed,confColor}) {
    const color=tc(t.abbr)
    const fillColor = t.abbr==='BRK' ? tt(t.abbr) : color
    const barPct=maxRS>minRS?((t.rsRating-minRS)/(maxRS-minRS))*100:50
    const [hovered,setHovered]=useState(false)
    return(
      <tr style={{
        borderBottom:`1px solid ${C.border}`,
        borderLeft:`4px solid ${fillColor}`,
        background:hovered?C.bg:'transparent',
        transition:'background 0.1s'}}
        onMouseEnter={()=>setHovered(true)}
        onMouseLeave={()=>setHovered(false)}>
        {/* Seed */}
        <td style={{padding:'0 8px 0 6px',fontFamily:mono,fontSize:12,
          color:C.text2,width:26,textAlign:'right',fontWeight:600}}>{seed}</td>
        {/* Team name + logo */}
        <td style={{padding:'9px 8px'}}>
          <div style={{display:'flex',alignItems:'center',gap:8}}>
            <div style={{width:32,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}>
              <TeamLogo abbr={t.abbr} size={24} />
            </div>
            <div style={{fontSize:12,fontWeight:600,color:C.text,lineHeight:1}}>{t.name}</div>
          </div>
        </td>
        {/* W */}
        <td style={{padding:'0 8px',fontFamily:mono,fontSize:12,fontWeight:600,color:C.text,textAlign:'right'}}>{t.w}</td>
        {/* L */}
        <td style={{padding:'0 8px',fontFamily:mono,fontSize:12,color:C.text2,textAlign:'right'}}>{t.l}</td>
        {/* Pct */}
        <td style={{padding:'0 8px',fontFamily:mono,fontSize:11,color:C.text2,textAlign:'right'}}>
          {(winPct(t)*100).toFixed(1)}%
        </td>
        {/* RS Rating + bar */}
        <td style={{padding:'0 10px 0 6px',textAlign:'right'}}>
          <div style={{display:'flex',alignItems:'center',gap:6,justifyContent:'flex-end'}}>
            <div style={{width:50,height:3,background:C.border,borderRadius:2,flexShrink:0}}>
              <div style={{width:`${barPct}%`,height:3,borderRadius:2,background:fillColor}}/>
            </div>
            <span style={{fontFamily:mono,fontSize:12,fontWeight:600,color:C.text,minWidth:44,textAlign:'right'}}>
              {t.rsRating?.toFixed(1)??'—'}
            </span>
          </div>
        </td>
        {/* Playoff */}
        <td style={{padding:'0 8px'}}><PlayoffBadge abbr={t.abbr}/></td>
      </tr>
    )
  }

  function GroupSep({label,color,shade}) {
    return(
      <tr>
        <td colSpan={7} style={{padding:0}}>
          <div style={{display:'flex',alignItems:'center',gap:8,padding:'5px 10px',
            background:shade,borderTop:`2px solid ${color}40`,borderBottom:`1px solid ${color}20`}}>
            <div style={{width:6,height:6,borderRadius:'50%',background:color,flexShrink:0}}/>
            <span style={{fontFamily:mono,fontSize:8,fontWeight:700,color,textTransform:'uppercase',letterSpacing:1.5}}>
              {label}
            </span>
          </div>
        </td>
      </tr>
    )
  }

  const tableHead=(confColor)=>(
    <thead>
      <tr>
        <TH label="#" align="right"/>
        <TH label="Team" align="left"/>
        <TH label="W"/>
        <TH label="L"/>
        <TH label="Pct"/>
        <TH label="RS Rating"/>
        <TH label="Playoff" align="left"/>
      </tr>
    </thead>
  )

  function ConferenceTable({confName}) {
    const confColor=confName==='East'?C.acc:C.ut
    const overrides=confName==='West'?WEST_SEED_OVERRIDES:EAST_SEED_OVERRIDES
    const sortFn=standingsSortWithOverrides(overrides)
    const cTeams=teams.filter(t=>t.conf===confName).sort(sortFn)
    const auto=cTeams.slice(0,6), playIn=cTeams.slice(6,10), lottery=cTeams.slice(10)

    if(view==='conference') return(
      <div style={{flex:'1 1 0',minWidth:0}}>
        <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:12}}>
          <span style={{fontFamily:mono,fontSize:11,fontWeight:700,color:confColor,textTransform:'uppercase',letterSpacing:2}}>
            {confName}ern Conference
          </span>
          <div style={{flex:1,height:1,background:C.border}}/>
        </div>
        <div style={{background:'#fff',border:`1px solid ${C.border}`,borderRadius:10,overflow:'hidden'}}>
          <table style={{width:'100%',borderCollapse:'collapse'}}>
            {tableHead(confColor)}
            <tbody>
              <GroupSep label="Automatic Playoff Berths · Seeds 1–6" color={C.uo} shade={`${C.uo}12`}/>
              {auto.map((t,i)=><TeamRow key={t.abbr} t={t} seed={i+1} confColor={confColor}/>)}
              <GroupSep label="Play-In Tournament · Seeds 7–10" color={C.ut} shade={`${C.ut}10`}/>
              {playIn.map((t,i)=><TeamRow key={t.abbr} t={t} seed={i+7} confColor={confColor}/>)}
              <GroupSep label="Lottery · Seeds 11–15" color={C.acc} shade={`${C.acc}0e`}/>
              {lottery.map((t,i)=><TeamRow key={t.abbr} t={t} seed={i+11} confColor={confColor}/>)}
            </tbody>
          </table>
        </div>
      </div>
    )

    // Division view
    return(
      <div style={{flex:'1 1 0',minWidth:0}}>
        <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:12}}>
          <span style={{fontFamily:mono,fontSize:11,fontWeight:700,color:confColor,textTransform:'uppercase',letterSpacing:2}}>
            {confName}ern Conference
          </span>
          <div style={{flex:1,height:1,background:C.border}}/>
        </div>
        <div style={{display:'flex',flexDirection:'column',gap:14}}>
          {Object.entries(DIVISIONS[confName]).map(([divName,abbrs])=>{
            const sorted=abbrs.map(a=>teamMap[a]).filter(Boolean).sort(sortFn)
            const confSorted=[...teams].filter(t=>t.conf===confName).sort(sortFn)
            const confSeedMap={}; confSorted.forEach((t,i)=>{confSeedMap[t.abbr]=i+1})
            return(
              <div key={divName} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:10,overflow:'hidden'}}>
                <div style={{padding:'5px 10px',background:C.bg,borderBottom:`1px solid ${C.border}`,
                  display:'flex',alignItems:'center',gap:8}}>
                  <span style={{fontFamily:mono,fontSize:9,fontWeight:700,color:confColor,textTransform:'uppercase',letterSpacing:1.5}}>
                    {divName} Division
                  </span>
                  {sorted[0]&&<span style={{fontFamily:mono,fontSize:8,color:C.ut,
                    background:'rgba(191,87,0,0.1)',padding:'1px 5px',borderRadius:3,fontWeight:700}}>
                    Leader: {sorted[0].abbr}
                  </span>}
                </div>
                <table style={{width:'100%',borderCollapse:'collapse'}}>
                  {tableHead(confColor)}
                  <tbody>{sorted.map(t=><TeamRow key={t.abbr} t={t} seed={confSeedMap[t.abbr]??null} confColor={confColor}/>)}</tbody>
                </table>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  return(
    <div>
      <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:20}}>
        <div style={{display:'flex',background:C.border,borderRadius:8,overflow:'hidden',border:`1px solid ${C.border2}`}}>
          {[['conference','Conference'],['division','By Division']].map(([v,l])=>(
            <button key={v} onClick={()=>setView(v)} style={{
              fontFamily:mono,fontSize:11,padding:'5px 14px',cursor:'pointer',border:'none',
              background:view===v?C.acc:'transparent',color:view===v?'#fff':C.text2,transition:'all 0.15s'}}>
              {l}
            </button>
          ))}
        </div>
        <span style={{marginLeft:'auto',fontFamily:mono,fontSize:10,color:C.text3}}>
          Sorted by win% · RS Ratings only · Tiebreak: wins
        </span>
      </div>
      {/* Both conferences side by side, seed 1 next to seed 1 */}
      <div style={{display:'flex',gap:24,alignItems:'flex-start'}}>
        <ConferenceTable confName="West"/>
        <ConferenceTable confName="East"/>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// BracketTab — stacked layout: East on top, West below, both flow left→right
// to a shared Finals column. No SVG connector lines.
// ─────────────────────────────────────────────────────────────────────────────
function BracketTab({poGames,teams}) {
  const [bracketView,setBracketView]=useState('playoffs')

  const teamMap={}; for(const t of teams) teamMap[t.abbr]=t
  const series=buildBracket(poGames)

  // Seeds from RS standings, consistent with Standings tab
  const eastSorted=[...teams].filter(t=>EAST_TEAMS.has(t.abbr)).sort(standingsSortWithOverrides(EAST_SEED_OVERRIDES))
  const westSorted=[...teams].filter(t=>WEST_TEAMS.has(t.abbr)).sort(standingsSortWithOverrides(WEST_SEED_OVERRIDES))
  const seedMap={}
  eastSorted.forEach((t,i)=>{seedMap[t.abbr]=i+1})
  westSorted.forEach((t,i)=>{seedMap[t.abbr]=i+1})

  const isEast=s=>EAST_TEAMS.has(s.t1)&&EAST_TEAMS.has(s.t2)
  const isWest=s=>WEST_TEAMS.has(s.t1)&&WEST_TEAMS.has(s.t2)
  const byRound=(rnd,pred)=>series.filter(s=>s.round===String(rnd)&&pred(s))

  const westR1=byRound(1,isWest), westR2=byRound(2,isWest), westR3=byRound(3,isWest)
  const eastR1=byRound(1,isEast), eastR2=byRound(2,isEast), eastR3=byRound(3,isEast)
  const finals=byRound(4,()=>true)
  const playIn=series.filter(s=>s.round==='0.5')
  const champion=finals.find(s=>s.winner)

  // ── Seed-agnostic play-in game detection ──────────────────────────────────
  function detectPlayInGames(confPlayIn) {
    if(!confPlayIn.length) return {game78:null,game910:null,secondary:null}
    if(confPlayIn.length===1) return {game78:confPlayIn[0],game910:null,secondary:null}
    if(confPlayIn.length===2) {
      const [a,b]=confPlayIn
      const teamsA=new Set([a.t1,a.t2])
      const teamsB=new Set([b.t1,b.t2])
      const shared=[...teamsA].some(t=>teamsB.has(t))
      if(shared) {
        if(b.loser&&teamsA.has(b.loser)) return {game78:b,game910:null,secondary:a}
        if(a.loser&&teamsB.has(a.loser)) return {game78:a,game910:null,secondary:b}
        return {game78:a,game910:null,secondary:b}
      }
      return {game78:a,game910:b,secondary:null}
    }
    for(let i=0;i<confPlayIn.length;i++) {
      const s=confPlayIn[i]
      const others=confPlayIn.filter((_,j)=>j!==i)
      const teamsS=new Set([s.t1,s.t2])
      const sharesWithBoth=others.every(o=>[o.t1,o.t2].some(t=>teamsS.has(t)))
      if(sharesWithBoth) {
        const [o1,o2]=others
        if(o1.loser&&teamsS.has(o1.loser)) return {game78:o1,game910:o2,secondary:s}
        return {game78:o2,game910:o1,secondary:s}
      }
    }
    return {game78:confPlayIn[0],game910:confPlayIn[1],secondary:confPlayIn[2]||null}
  }

  const westPI=detectPlayInGames(playIn.filter(isWest))
  const eastPI=detectPlayInGames(playIn.filter(isEast))

  // Snapshot seeds BEFORE patching — used for display ordering in play-in bracket
  const prePatchSeedMap={...seedMap}

  // ── Patch seedMap with confirmed play-in seeds ────────────────────────────
  function patchPlayInSeeds(pi) {
    if(pi.game78?.winner)    seedMap[pi.game78.winner]=7
    if(pi.secondary?.winner) seedMap[pi.secondary.winner]=8
    if(pi.secondary?.loser)  seedMap[pi.secondary.loser]=9
    if(!pi.secondary?.winner&&pi.game78?.loser) seedMap[pi.game78.loser]=8
    if(pi.game910?.winner&&!pi.secondary?.winner) seedMap[pi.game910.winner]=9
  }
  patchPlayInSeeds(westPI)
  patchPlayInSeeds(eastPI)

  // ── Placeholder series builder ────────────────────────────────────────────
  function placeholder(t1,t2) {
    return {t1:t1||null,t2:t2||null,w1:0,w2:0,winner:null,loser:null,
      games:[],latestRating:{},latestDate:'',round:null,maxWins:4}
  }

  function findOrBuild(r1a,r1b,existingList,fallbackIdx) {
    const wa=r1a?.winner, wb=r1b?.winner
    if(wa&&wb) {
      const found=existingList.find(s=>(s.t1===wa||s.t2===wa)&&(s.t1===wb||s.t2===wb))
      if(found) return found
    }
    if(wa) {
      const found=existingList.find(s=>s.t1===wa||s.t2===wa)
      if(found) return found
    }
    if(wb) {
      const found=existingList.find(s=>s.t1===wb||s.t2===wb)
      if(found) return found
    }
    if(wa||wb) return placeholder(wa||null,wb||null)
    return existingList[fallbackIdx]||existingList[0]||null
  }

  function findOrBuildCF(r2a,r2b,existingList) {
    const wa=r2a?.winner, wb=r2b?.winner
    if(wa&&wb) {
      const found=existingList.find(s=>(s.t1===wa||s.t2===wa)&&(s.t1===wb||s.t2===wb))
      if(found) return found
      return placeholder(wa,wb)
    }
    if(wa) {
      const found=existingList.find(s=>s.t1===wa||s.t2===wa)
      if(found) return found
      return placeholder(wa,null)
    }
    if(wb) {
      const found=existingList.find(s=>s.t1===wb||s.t2===wb)
      if(found) return found
      return placeholder(wb,null)
    }
    return existingList[0]||null
  }

  function findOrBuildFinals(cfE,cfW,existingList) {
    if(existingList.length) return existingList[0]
    const wa=cfE?.winner, wb=cfW?.winner
    if(wa||wb) return placeholder(wa||null,wb||null)
    return null
  }


  // ── Sort helpers ──────────────────────────────────────────────────────────
  function sortBySeed(list) {
    return [...list].sort((a,b)=>{
      const aMin=Math.min(seedMap[a.t1]||99,seedMap[a.t2]||99)
      const bMin=Math.min(seedMap[b.t1]||99,seedMap[b.t2]||99)
      return aMin-bMin
    })
  }

  function bracketOrder(list) {
    const sorted=sortBySeed(list)
    const find=(a,b)=>sorted.find(s=>{
      const seeds=[seedMap[s.t1]||0,seedMap[s.t2]||0].sort((x,y)=>x-y)
      return seeds[0]===a&&seeds[1]===b
    })||null
    return [find(1,8),find(4,5),find(2,7),find(3,6)]
  }

  const eR1o=bracketOrder(eastR1)
  const wR1o=bracketOrder(westR1)

  const eR2top=findOrBuild(eR1o[0],eR1o[1],eastR2,0)
  const eR2bot=findOrBuild(eR1o[2],eR1o[3],eastR2.filter(s=>s!==eR2top),1)
  const wR2top=findOrBuild(wR1o[0],wR1o[1],westR2,0)
  const wR2bot=findOrBuild(wR1o[2],wR1o[3],westR2.filter(s=>s!==wR2top),1)

  const eCF=findOrBuildCF(eR2top,eR2bot,eastR3)
  const wCF=findOrBuildCF(wR2top,wR2bot,westR3)
  const fin=findOrBuildFinals(eCF,wCF,finals)

  // ── Layout constants ──────────────────────────────────────────────────────
  const CARD_H=76
  const CARD_GAP=5
  const PAIR_GAP=14
  const LABEL_H=30

  const PAIR_H=CARD_H*2+CARD_GAP
  const r2Top=(i)=>i*(PAIR_H+PAIR_GAP)+(PAIR_H-CARD_H)/2
  const r2BotTop=r2Top(1)
  const CONF_H=r2BotTop+CARD_H
  const cfTopVal=(r2Top(0)+CARD_H/2+r2BotTop+CARD_H/2)/2-CARD_H/2
  // Finals sits below the bottom edge of both CF cards
  const cfBottomEdge=cfTopVal+CARD_H
  const finTopVal=cfBottomEdge+20

  const CW={r1:152,r2:152,cf:152,finals:202}

  // ── Team row ──────────────────────────────────────────────────────────────
  function BracketTeamRow({abbr,wins,isWinner,isLoser,seriesObj,isPlayIn=false,piScore,cardH=CARD_H}) {
    if(!abbr) return(
      <div style={{height:cardH/2,display:'flex',alignItems:'center',padding:'0 10px',
        borderLeft:'3px solid transparent'}}>
        <span style={{fontFamily:mono,fontSize:11,color:'rgba(255,255,255,0.25)'}}>TBD</span>
      </div>
    )
    const color=tc(abbr)
    const sec=ts(abbr)
    const seed=seedMap[abbr]
    // Rating = end-of-series rating from this specific series, fallback to rsRating
    const rating = seriesObj?.latestRating?.[abbr] ?? teamMap[abbr]?.rsRating ?? null
    const displayScore=isPlayIn?piScore:wins
    const scale=cardH/CARD_H
    return(
      <div style={{
        height:cardH/2,display:'flex',alignItems:'center',overflow:'hidden',
        background:`${color}cc`,
        borderLeft:isWinner?`3px solid ${color}`:'3px solid transparent',
        paddingRight:6,
        position:'relative',
      }}>
        {/* Seed */}
        <div style={{width:Math.round(26*scale),textAlign:'center',fontFamily:mono,
          fontSize:Math.round(13*scale),color:sec,
          flexShrink:0,fontWeight:isWinner?700:600}}>
          {seed??'—'}
        </div>
        {/* Logo */}
        <div style={{width:Math.round(30*scale),display:'flex',alignItems:'center',
          justifyContent:'center',flexShrink:0,marginRight:Math.round(3*scale)}}>
          <TeamLogo abbr={abbr} size={Math.round(20*scale)}/>
        </div>
        {/* Abbr pill — fixed width so 2- and 3-letter badges align */}
        <div style={{fontFamily:mono,fontSize:Math.round(9*scale),fontWeight:700,
          padding:`${Math.round(1*scale)}px ${Math.round(4*scale)}px`,borderRadius:3,
          flexShrink:0,minWidth:Math.round(32*scale),textAlign:'center',
          border:`1.5px solid ${sec}`,color:sec,background:'transparent',
          marginRight:Math.round(5*scale),letterSpacing:0.3}}>{abbr}</div>
        {/* Rating */}
        {rating!=null&&(
          <div style={{fontFamily:mono,fontSize:Math.round(11*scale),
            color:sec,opacity:0.75,flexShrink:0,fontWeight:500}}>
            {rating.toFixed(0)}
          </div>
        )}
        <div style={{flex:1}}/>
        {/* Win count */}
        <div style={{fontFamily:mono,fontSize:Math.round(20*scale),fontWeight:900,
          flexShrink:0,minWidth:Math.round(18*scale),textAlign:'center',lineHeight:1,
          color:sec,
          opacity:1,
          textShadow:isWinner?`0 0 10px ${color}60`:'none',marginRight:Math.round(6*scale)}}>{displayScore??''}</div>
      </div>
    )
  }

  // ── Series card ───────────────────────────────────────────────────────────
  function BracketCard({s,isPlayIn=false,cardH=CARD_H}) {
    if(!s) return(
      <div style={{
        background:'rgba(255,255,255,0.4)',
        border:'1px dashed rgba(0,0,0,0.15)',
        borderRadius:8,overflow:'hidden',height:cardH,
        display:'flex',alignItems:'center',justifyContent:'center'}}>
        <span style={{fontFamily:mono,fontSize:10,color:'rgba(0,0,0,0.3)',letterSpacing:0.5}}>TBD</span>
      </div>
    )

    let {t1,t2,w1,w2,winner}=s
    if(t1&&t2) {
      const s1=seedMap[t1]??99, s2=seedMap[t2]??99
      if(s2<s1) { [t1,t2]=[t2,t1]; [w1,w2]=[w2,w1] }
    }

    const hasStarted=w1>0||w2>0
    const isActive=!winner&&hasStarted
    const isComplete=!!winner
    const winnerColor=winner?tc(winner):null

    return(
      <div style={{
        background:'transparent',
        borderRadius:8,overflow:'hidden',
        border:isActive
          ?`1.5px solid ${C.acc}80`
          :isComplete
          ?`1px solid ${winnerColor}50`
          :`1px solid rgba(0,0,0,0.12)`,
        boxShadow:isActive
          ?`0 2px 16px ${C.acc}20`
          :isComplete
          ?`0 2px 12px ${winnerColor}20`
          :`0 1px 3px rgba(0,0,0,0.08)`,
        position:'relative',
      }}>
        <div style={{position:'absolute',top:0,left:0,right:0,height:1,
          background:'rgba(255,255,255,0.3)',zIndex:1,pointerEvents:'none'}}/>
        <BracketTeamRow abbr={t1} wins={w1} isWinner={winner===t1}
          isLoser={!!(winner&&winner!==t1)} seriesObj={s} isPlayIn={isPlayIn}
          piScore={null} cardH={cardH}/>
        <div style={{height:1,background:isComplete?`${winnerColor}30`:'rgba(0,0,0,0.08)'}}/>
        <BracketTeamRow abbr={t2} wins={w2} isWinner={winner===t2}
          isLoser={!!(winner&&winner!==t2)} seriesObj={s} isPlayIn={isPlayIn}
          piScore={null} cardH={cardH}/>
      </div>
    )
  }

  // ── Conference bracket half ───────────────────────────────────────────────
  function ConfBracket({r1,r2top,r2bot,cf,confColor,confName,mirror=false}) {
    const cols = mirror
      ? [
          {w:CW.cf, render:()=>(
            <div style={{width:CW.cf,flexShrink:0,position:'relative',height:CONF_H}}>
              <div style={{position:'absolute',top:cfTopVal,left:0,right:0}}>
                <BracketCard s={cf||null}/>
              </div>
            </div>
          )},
          {w:CW.r2, render:()=>(
            <div style={{width:CW.r2,flexShrink:0,position:'relative',height:CONF_H}}>
              {[[r2top,r2Top(0)],[r2bot,r2BotTop]].map(([s,top],i)=>(
                <div key={i} style={{position:'absolute',top,left:0,right:0}}>
                  <BracketCard s={s||null}/>
                </div>
              ))}
            </div>
          )},
          {w:CW.r1, render:()=>(
            <div style={{width:CW.r1,flexShrink:0,height:CONF_H,position:'relative'}}>
              <div style={{position:'absolute',top:0,left:0,right:0,display:'flex',flexDirection:'column',gap:0}}>
                {[0,1,2,3].map(i=>(
                  <div key={i}>
                    {i===2&&<div style={{height:PAIR_GAP}}/>}
                    {i>0&&i!==2&&<div style={{height:CARD_GAP}}/>}
                    <BracketCard s={r1[i]||null}/>
                  </div>
                ))}
              </div>
            </div>
          )},
        ]
      : [
          {w:CW.r1, render:()=>(
            <div style={{width:CW.r1,flexShrink:0,height:CONF_H,position:'relative'}}>
              <div style={{position:'absolute',top:0,left:0,right:0,display:'flex',flexDirection:'column',gap:0}}>
                {[0,1,2,3].map(i=>(
                  <div key={i}>
                    {i===2&&<div style={{height:PAIR_GAP}}/>}
                    {i>0&&i!==2&&<div style={{height:CARD_GAP}}/>}
                    <BracketCard s={r1[i]||null}/>
                  </div>
                ))}
              </div>
            </div>
          )},
          {w:CW.r2, render:()=>(
            <div style={{width:CW.r2,flexShrink:0,position:'relative',height:CONF_H}}>
              {[[r2top,r2Top(0)],[r2bot,r2BotTop]].map(([s,top],i)=>(
                <div key={i} style={{position:'absolute',top,left:0,right:0}}>
                  <BracketCard s={s||null}/>
                </div>
              ))}
            </div>
          )},
          {w:CW.cf, render:()=>(
            <div style={{width:CW.cf,flexShrink:0,position:'relative',height:CONF_H}}>
              <div style={{position:'absolute',top:cfTopVal,left:0,right:0}}>
                <BracketCard s={cf||null}/>
              </div>
            </div>
          )},
        ]

    return(
      <div>
        {/* Conference label */}
        <div style={{display:'flex',alignItems:'center',gap:10,height:30,
          flexDirection:mirror?'row-reverse':'row'}}>
          <div style={{width:3,height:16,borderRadius:2,background:confColor,flexShrink:0}}/>
          <span style={{fontFamily:mono,fontSize:11,fontWeight:700,color:confColor,
            textTransform:'uppercase',letterSpacing:2}}>{confName}ern Conference</span>
          <div style={{flex:1,height:1,background:`${confColor}30`}}/>
        </div>
        <div style={{display:'flex',alignItems:'flex-start',gap:6,position:'relative'}}>
          {cols.map((col,i)=>(
            <div key={i} style={{flexShrink:0}}>{col.render()}</div>
          ))}
        </div>
      </div>
    )
  }

  // ── Finals column ─────────────────────────────────────────────────────────
  function FinalsCard({s}) {
    const finW=CW.finals
    if(!s) return(
      <div style={{width:finW,flexShrink:0}}>
        <div style={{fontFamily:mono,fontSize:10,fontWeight:700,color:C.ut,
          textTransform:'uppercase',letterSpacing:1.6,marginBottom:8,
          paddingBottom:8,borderBottom:`1px solid ${C.ut}40`,textAlign:'center'}}>
          NBA Finals
        </div>
        <div style={{background:'rgba(255,255,255,0.4)',border:'1px dashed rgba(0,0,0,0.15)',
          borderRadius:8,height:CARD_H,display:'flex',alignItems:'center',justifyContent:'center'}}>
          <span style={{fontFamily:mono,fontSize:10,color:'rgba(0,0,0,0.3)'}}>TBD</span>
        </div>
      </div>
    )

    let {t1,t2,w1,w2,winner}=s
    if(t1&&t2){
      const s1=seedMap[t1]??99,s2=seedMap[t2]??99
      if(s2<s1){[t1,t2]=[t2,t1];[w1,w2]=[w2,w1]}
    }
    const isComplete=!!winner
    const winnerColor=winner?tc(winner):null
    const FROW_H=52

    function FinalsTeamRow({abbr,wins,isWin}) {
      if(!abbr) return <div style={{height:FROW_H,display:'flex',alignItems:'center',padding:'0 12px'}}><span style={{fontFamily:mono,fontSize:11,color:'rgba(0,0,0,0.3)'}}>TBD</span></div>
      const color=tc(abbr)
      const sec=ts(abbr)
      const seed=seedMap[abbr]
      const rating=s.latestRating?.[abbr]??teamMap[abbr]?.rsRating??null
      return(
        <div style={{height:FROW_H,display:'flex',alignItems:'center',overflow:'hidden',position:'relative',
          background:`${color}cc`,
          borderLeft:isWin?`4px solid ${color}`:'4px solid transparent',
          paddingRight:8}}>
          {/* Seed */}
          <div style={{width:24,textAlign:'center',fontFamily:mono,fontSize:13,
            color:sec,fontWeight:isWin?700:600,flexShrink:0}}>{seed??'—'}</div>
          {/* Logo */}
          <div style={{width:34,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}>
            <TeamLogo abbr={abbr} size={24}/>
          </div>
          {/* Name + rating */}
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontFamily:mono,fontSize:10,fontWeight:700,color:sec,
              whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{tn(abbr)}</div>
            {rating!=null&&<div style={{fontFamily:mono,fontSize:11,color:sec,opacity:0.75,marginTop:1,fontWeight:500}}>{rating.toFixed(0)}</div>}
          </div>
          {/* Series wins */}
          <div style={{fontFamily:mono,fontSize:26,fontWeight:900,lineHeight:1,
            color:isWin?sec:'rgba(0,0,0,0.4)',
            textShadow:isWin?`0 0 12px ${color}80`:'none',
            marginLeft:4,flexShrink:0}}>{wins}</div>
        </div>
      )
    }

    return(
      <div style={{width:finW,flexShrink:0}}>
        <div style={{fontFamily:mono,fontSize:10,fontWeight:700,color:C.ut,
          textTransform:'uppercase',letterSpacing:1.6,marginBottom:8,
          paddingBottom:8,borderBottom:`1px solid ${C.ut}40`,textAlign:'center'}}>
          NBA Finals
        </div>
        <div style={{borderRadius:8,overflow:'hidden',
          border:isComplete?`1px solid ${winnerColor}50`:'1px solid rgba(0,0,0,0.12)',
          boxShadow:isComplete?`0 2px 12px ${winnerColor}20`:'0 1px 3px rgba(0,0,0,0.08)'}}>
          <FinalsTeamRow abbr={t1} wins={w1} isWin={winner===t1||(!winner&&w1>=w2)}/>
          <div style={{height:1,background:isComplete?`${winnerColor}30`:'rgba(0,0,0,0.08)'}}/>
          <FinalsTeamRow abbr={t2} wins={w2} isWin={winner===t2||(!winner&&w2>w1)}/>
        </div>
      </div>
    )
  }

  // ── Column headers row ────────────────────────────────────────────────────
  function BracketHeaders() {
    // Determine the current active round:
    // - If a round has any in-progress series (started, no winner) → that's active
    // - Otherwise advance to the next round as soon as the previous round is fully complete
    // - This means Finals is active as soon as both conf finals are done, even pre-game-1
    const allSeries=[...series]
    let activeRound=1
    for(const rnd of [1,2,3,4]){
      const inRound=allSeries.filter(s=>s.round===String(rnd))
      if(!inRound.length) break
      const anyInProgress=inRound.some(s=>!s.winner&&(s.w1>0||s.w2>0))
      const allDone=inRound.every(s=>s.winner)
      if(anyInProgress){activeRound=rnd;break}
      activeRound=rnd          // this round is done (or pending), mark it and keep checking
      if(!allDone) break       // some not yet started but none in progress → still this round
    }
    // Map round number to column label keys
    const roundToKey={1:'r1',2:'r2',3:'cf',4:'finals'}
    const activeKey=roundToKey[activeRound]

    const glowColor='#D4AF37'
    const h=(label,w,colKey,align='center')=>{
      const isActive=colKey===activeKey
      return(
        <div style={{width:w,flexShrink:0,fontFamily:mono,fontSize:9,fontWeight:isActive?900:700,
          color:isActive?glowColor:'rgba(0,0,0,0.45)',
          textTransform:'uppercase',letterSpacing:1.6,
          paddingBottom:8,
          borderBottom:isActive?`2px solid ${glowColor}`:`1px solid rgba(0,0,0,0.15)`,
          marginBottom:12,textAlign:align,
          textShadow:isActive?`0 0 10px ${glowColor}90`:'none',
          transition:'all 0.2s'}}>
          {label}
        </div>
      )
    }
    return(
      <div style={{display:'flex',gap:6,marginBottom:0}}>
        {h('Round 1',CW.r1,'r1')}
        {h('Conf Semis',CW.r2,'r2')}
        {h('Conf Finals',CW.cf,'cf')}
        {h('NBA Finals',CW.finals,'finals','center')}
        {h('Conf Finals',CW.cf,'cf')}
        {h('Conf Semis',CW.r2,'r2')}
        {h('Round 1',CW.r1,'r1')}
      </div>
    )
  }

  // ── PLAY-IN BRACKET ───────────────────────────────────────────────────────
  function PlayInBracket() {
    const {game78:west78,game910:west910,secondary:westSecondary}=westPI
    const {game78:east78,game910:east910,secondary:eastSecondary}=eastPI

    function PICard({s}) {
      if(!s) return(
        <div style={{background:'rgba(255,255,255,0.4)',border:`1px dashed rgba(0,0,0,0.15)`,borderRadius:8,
          height:CARD_H,display:'flex',alignItems:'center',justifyContent:'center'}}>
          <span style={{fontFamily:mono,fontSize:10,color:'rgba(0,0,0,0.3)'}}>TBD</span>
        </div>
      )
      const game = s.games.find(g => g.home_away === 'H') || s.games[0]
      const homeTeam = game?.team_id
      const awayTeam = game?.opponent_id
      const homeScore = game?.points_for ?? null
      const awayScore = game?.points_against ?? null

      let {t1, t2} = s
      if(t1&&t2){const s1=prePatchSeedMap[t1]??99,s2=prePatchSeedMap[t2]??99; if(s2<s1){[t1,t2]=[t2,t1]}}

      const score1 = t1===homeTeam ? homeScore : t1===awayTeam ? awayScore : null
      const score2 = t2===homeTeam ? homeScore : t2===awayTeam ? awayScore : null
      const isComplete = !!s.winner
      const winnerColor = s.winner ? tc(s.winner) : null

      function PIRow({abbr,score,isWin}) {
        if(!abbr) return <div style={{height:CARD_H/2,display:'flex',alignItems:'center',padding:'0 10px'}}><span style={{fontFamily:mono,fontSize:10,color:'rgba(0,0,0,0.3)'}}>TBD</span></div>
        const color=tc(abbr)
        const sec=ts(abbr)
        const seed=prePatchSeedMap[abbr]
        return(
          <div style={{height:CARD_H/2,display:'flex',alignItems:'center',overflow:'hidden',
            background:`${color}cc`,
            borderLeft:isWin?`3px solid ${color}`:'3px solid transparent',
            paddingRight:6,position:'relative'}}>
            <div style={{width:22,textAlign:'center',fontFamily:mono,fontSize:10,
              color:sec,fontWeight:isWin?700:500,flexShrink:0}}>{seed??'—'}</div>
            <div style={{width:28,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0,marginRight:2}}>
              <TeamLogo abbr={abbr} size={18}/>
            </div>
            <div style={{fontFamily:mono,fontSize:9,fontWeight:700,
              minWidth:32,textAlign:'center',
              padding:'1px 4px',borderRadius:3,flexShrink:0,
              border:`1.5px solid ${sec}`,color:sec,
              background:'transparent',marginRight:4,letterSpacing:0.3}}>{abbr}</div>
            <div style={{flex:1}}/>
            {score!=null&&<div style={{fontFamily:mono,fontSize:18,fontWeight:900,
              color:isWin?sec:'rgba(0,0,0,0.5)',
              textShadow:isWin?`0 0 10px ${color}60`:'none',
              marginRight:4}}>{score}</div>}
          </div>
        )
      }

      return(
        <div style={{
          borderRadius:8,overflow:'hidden',
          border:isComplete?`1px solid ${winnerColor}50`:`1px solid rgba(0,0,0,0.12)`,
          boxShadow:isComplete?`0 2px 12px ${winnerColor}20`:`0 1px 3px rgba(0,0,0,0.08)`,
        }}>
          <PIRow abbr={t1} score={score1} isWin={s.winner===t1}/>
          <div style={{height:1,background:isComplete?`${winnerColor}30`:'rgba(0,0,0,0.08)'}}/>
          <PIRow abbr={t2} score={score2} isWin={s.winner===t2}/>
        </div>
      )
    }

    function PIConf({confName,game78,game910,secondary,confColor}) {
      const winner78=game78?.winner||null
      const secondary8=secondary?.winner||null
      return(
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontFamily:mono,fontSize:10,fontWeight:700,color:confColor,
            textTransform:'uppercase',letterSpacing:2,marginBottom:12,
            paddingBottom:6,borderBottom:`1px solid rgba(0,0,0,0.12)`}}>
            {confName}ern Conference
          </div>
          <div style={{display:'flex',gap:12,alignItems:'flex-start'}}>
            <div style={{flex:1,minWidth:0}}>
              <div style={{fontFamily:mono,fontSize:8,color:'rgba(0,0,0,0.45)',textTransform:'uppercase',
                letterSpacing:1,marginBottom:5,fontWeight:600}}>7 vs 8 · winner = 7-seed</div>
              <PICard s={game78}/>
              {winner78&&(
                <div style={{display:'flex',alignItems:'center',gap:5,marginTop:6,padding:'4px 7px',
                  background:`rgba(255,255,255,0.06)`,border:`1px solid rgba(255,255,255,0.12)`,borderRadius:5}}>
                  <span style={{fontFamily:mono,fontSize:8,color:confColor,fontWeight:700}}>7-seed →</span>
                  <TeamLogo abbr={winner78} size={14}/>
                  <span style={{fontFamily:mono,fontSize:9,fontWeight:700,color:tc(winner78),
                    padding:'1px 4px',borderRadius:3,border:`1.5px solid ${tc(winner78)}`,
                    background:`${tc(winner78)}20`}}>{winner78}</span>
                </div>
              )}
            </div>
            <div style={{flex:1,minWidth:0}}>
              <div style={{fontFamily:mono,fontSize:8,color:'rgba(0,0,0,0.45)',textTransform:'uppercase',
                letterSpacing:1,marginBottom:5,fontWeight:600}}>9 vs 10</div>
              <PICard s={game910}/>
              <div style={{marginTop:10}}>
                <div style={{fontFamily:mono,fontSize:8,color:'rgba(0,0,0,0.45)',textTransform:'uppercase',
                  letterSpacing:1,marginBottom:5,fontWeight:600}}>
                  9/10 winner vs 7/8 loser · winner = 8-seed
                </div>
                <PICard s={secondary}/>
                {secondary8&&(
                  <div style={{display:'flex',alignItems:'center',gap:5,marginTop:6,padding:'4px 7px',
                    background:`rgba(255,255,255,0.06)`,border:`1px solid rgba(255,255,255,0.12)`,borderRadius:5}}>
                    <span style={{fontFamily:mono,fontSize:8,color:confColor,fontWeight:700}}>8-seed →</span>
                    <TeamLogo abbr={secondary8} size={14}/>
                    <span style={{fontFamily:mono,fontSize:9,fontWeight:700,color:tc(secondary8),
                      padding:'1px 4px',borderRadius:3,border:`1.5px solid ${tc(secondary8)}`,
                      background:`${tc(secondary8)}20`}}>{secondary8}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )
    }

    return(
      <div style={{
        background:'#DDD5C4',
        borderRadius:14,padding:'20px 18px 24px',
        boxShadow:'0 4px 24px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.4)',
        border:'1px solid #C8BFB1',
        position:'relative',overflow:'hidden',
        width:'fit-content',margin:'0 auto',
      }}>
        <div style={{position:'absolute',top:0,left:'50%',transform:'translateX(-50%)',
          width:'80%',height:'40%',borderRadius:'50%',
          background:'radial-gradient(ellipse, rgba(255,255,255,0.04) 0%, transparent 70%)',
          pointerEvents:'none'}}/>
        <div style={{display:'flex',alignItems:'center',gap:12,marginBottom:20}}>
          <div style={{flex:1,height:1,background:'rgba(0,0,0,0.12)'}}/>
          <span style={{fontFamily:mono,fontSize:10,fontWeight:700,color:'rgba(0,0,0,0.45)',
            textTransform:'uppercase',letterSpacing:2}}>Play-In Tournament 2025–26</span>
          <div style={{flex:1,height:1,background:'rgba(0,0,0,0.12)'}}/>
        </div>
        <div style={{display:'flex',gap:28}}>
          <PIConf confName="East" game78={east78} game910={east910}
            secondary={eastSecondary} confColor='rgba(102,51,153,0.9)'/>
          <PIConf confName="West" game78={west78} game910={west910}
            secondary={westSecondary} confColor='rgba(191,87,0,0.9)'/>
        </div>
        <div style={{marginTop:16,padding:'10px 14px',
          background:'rgba(255,255,255,0.5)',
          border:`1px solid rgba(0,0,0,0.1)`,borderRadius:8,
          fontFamily:mono,fontSize:10,color:'rgba(0,0,0,0.55)'}}>
          <strong style={{color:'rgba(0,0,0,0.75)'}}>How it works:</strong> The 7 vs 8 winner earns the 7-seed directly.
          The loser plays the 9 vs 10 winner — that winner earns the 8-seed.
        </div>
      </div>
    )
  }

  // ── Main render ───────────────────────────────────────────────────────────
  return(
    <div>
      <div style={{display:'flex',gap:8,marginBottom:20}}>
        {[['playoffs','Playoff Bracket'],['playin','Play-In Tournament']].map(([v,l])=>(
          <button key={v} onClick={()=>setBracketView(v)} style={{
            fontFamily:mono,fontSize:11,padding:'5px 14px',borderRadius:6,cursor:'pointer',
            border:`1px solid ${bracketView===v?C.acc:C.border2}`,
            background:bracketView===v?C.acc:'transparent',
            color:bracketView===v?'#fff':C.text2,transition:'all 0.15s',
          }}>{l}</button>
        ))}
        <span style={{marginLeft:'auto',fontFamily:mono,fontSize:9,color:C.text3,alignSelf:'center'}}>
          Seeds reflect RS standings (win%) · Ratings = latest in series
        </span>
      </div>

      {bracketView==='playin'&&<PlayInBracket/>}

      {bracketView==='playoffs'&&(
        <div>
          <div style={{
            background:'#DDD5C4',
            borderRadius:14,padding:'16px 14px 20px',
            boxShadow:'0 4px 24px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.4)',
            border:'1px solid #C8BFB1',
            position:'relative',overflow:'hidden',
            width:'fit-content',
            margin:'0 auto',
          }}>
            <div style={{position:'absolute',top:0,left:'50%',transform:'translateX(-50%)',
              width:'80%',height:'40%',borderRadius:'50%',
              background:'radial-gradient(ellipse, rgba(255,255,255,0.04) 0%, transparent 70%)',
              pointerEvents:'none'}}/>
            <BracketHeaders/>
            {/* Use a relative container so Finals can be absolutely positioned below CF cards */}
            <div style={{display:'flex',gap:6,alignItems:'flex-start',position:'relative'}}>
              <ConfBracket
                r1={eR1o} r2top={eR2top} r2bot={eR2bot} cf={eCF}
                confColor='rgba(102,51,153,0.9)' confName="East" mirror={false}/>
              {/* Finals column: absolutely centred, top = LABEL_H + finTopVal */}
              <div style={{flexShrink:0,width:CW.finals,alignSelf:'stretch',position:'relative',minHeight:LABEL_H+finTopVal+CARD_H+20}}>
                {/* Champion banner in the blank space above the Finals card */}
                {champion&&(
                  <div style={{
                    position:'absolute',top:0,left:0,right:0,
                    display:'flex',flexDirection:'column',alignItems:'center',
                    justifyContent:'flex-start',
                    paddingTop:LABEL_H+6,
                    gap:8,
                  }}>
                    <TeamLogo abbr={champion.winner} size={64}/>
                    <div style={{textAlign:'center'}}>
                      <div style={{fontFamily:mono,fontSize:9,fontWeight:700,color:C.ut,
                        textTransform:'uppercase',letterSpacing:2,marginBottom:4}}>
                        2025–26 NBA Champion
                      </div>
                      <div style={{fontFamily:serif,fontSize:20,fontWeight:900,color:C.text,lineHeight:1.1}}>
                        {tn(champion.winner)}
                      </div>
                    </div>
                  </div>
                )}
                <div style={{position:'absolute',top:LABEL_H+finTopVal,left:0,right:0}}>
                  <FinalsCard s={fin}/>
                </div>
              </div>
              <ConfBracket
                r1={wR1o} r2top={wR2top} r2bot={wR2bot} cf={wCF}
                confColor='rgba(191,87,0,0.9)' confName="West" mirror={true}/>
            </div>
            <div style={{display:'flex',gap:20,marginTop:28,fontFamily:mono,fontSize:9,
              color:'rgba(0,0,0,0.35)',flexWrap:'wrap'}}>
              <span># = Conference seed (RS standings)</span>
              <span>Rating = end-of-series post-game rating</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Dashboard shell
// ─────────────────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [variant,setVariant]=useState('continelo')
  const [data,setData]=useState({teams:[],accuracy:null,poGames:[]})
  const [loading,setLoading]=useState(true)
  const [activeTab,setActiveTab]=useState('rankings')

  const [selectedDate,setSelectedDate]=useState(null)
  const [dateGames,setDateGames]=useState([])
  const [dateLoading,setDateLoading]=useState(true)
  const [latestDate,setLatestDate]=useState(null)

  useEffect(()=>{
    setLoading(true)
    getData(variant).then(d=>{setData(d);setLoading(false)})
  },[variant])

  // Seed the date picker with the most recent game date, once, on mount
  useEffect(()=>{
    getLatestGameDate(variant).then(d=>{
      setLatestDate(d)
      if(d) setSelectedDate(d)
    })
  },[])

  useEffect(()=>{
    if(!selectedDate) return
    setDateLoading(true)
    getGamesForDate(selectedDate,variant).then(g=>{setDateGames(g);setDateLoading(false)})
  },[selectedDate,variant])

  const {teams,accuracy,poGames}=data
  const maxRating=teams.length?Math.max(...teams.map(t=>t.rating)):1600
  const minRating=teams.length?Math.min(...teams.map(t=>t.rating)):1400

  const TAB_COLORS={rankings:C.acc,standings:C.ut,bracket:C.uo}
  const TABS=[
    {id:'rankings',label:'Power Rankings'},
    {id:'standings',label:'Standings'},
    {id:'bracket',label:'Playoff Bracket'},
  ]

  return(
    <div className="dash">
      <nav className="nav" style={{background:C.bg,borderBottom:`1px solid ${C.border2}`}}>
        <div className="nav-brand">
          <span className="brand-dot"/>
          <span>
            <span style={{color:'#663399'}}>TR</span><span style={{color:'#BF5700'}}>AC</span><span style={{color:'#154733'}}>ER</span>
          </span>
        </div>
        <div className="nav-links">
          <span className="nav-link active">Dashboard</span>
          <Link href="/season/2026" className="nav-link">Season</Link>
          <Link href="/all-time" className="nav-link">All-Time</Link>
          <Link href="/team/ny" className="nav-link">Teams</Link>
          <Link href="/about" className="nav-link">About</Link>
        </div>
        <div className="nav-right">
          <div className="variant-toggle">
            <button className={`vt-btn${variant==='continelo'?' active':''}`} onClick={()=>setVariant('continelo')}>Echo</button>
            <button className={`vt-btn${variant==='elo'?' active':''}`} onClick={()=>setVariant('elo')}>Pulse</button>
          </div>
        </div>
      </nav>

      <div className="color-stripe">
        <div className="stripe-acc"/><div className="stripe-ut"/><div className="stripe-uo"/>
      </div>

      <div className="hero">
        <div>
          <div className="hero-label">2025–26 Season · Playoffs</div>
          <div className="hero-heading">Dashboard</div>
          <div className="hero-sub">
            {variant==='continelo'
              ?'Echo ratings — carry-forward variant · Updated after every game'
              :'Pulse ratings — season-reset variant · Updated after every game'}
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{borderBottom:`1px solid ${C.border}`,background:'#fff',
        display:'flex',maxWidth:1280,margin:'0 auto',padding:'0 2rem'}}>
        {TABS.map(tab=>{
          const tabColor=TAB_COLORS[tab.id]
          return(
            <button key={tab.id} onClick={()=>setActiveTab(tab.id)} style={{
              fontSize:13,fontFamily:mono,padding:'12px 20px',cursor:'pointer',
              background:'none',border:'none',marginBottom:-1,
              borderBottom:activeTab===tab.id?`2px solid ${tabColor}`:'2px solid transparent',
              color:activeTab===tab.id?tabColor:C.text3,
              fontWeight:activeTab===tab.id?600:400,
              transition:'all 0.15s',whiteSpace:'nowrap',
            }}>{tab.label}</button>
          )
        })}
      </div>

      <div style={{maxWidth:1280,margin:'0 auto',padding:'1.5rem 2rem 4rem'}}>

        {/* Power Rankings */}
        {activeTab==='rankings'&&(
          <div className="main-grid">
            <div className="left-col">
              <div className="section-label">Current Ratings</div>
              {loading
                ?<div style={{color:C.text3,fontFamily:mono,fontSize:13,padding:'2rem 0'}}>Loading…</div>
                :(
                  <table className="ratings-table">
                    <thead>
                      <tr>
                        <th>#</th><th>Team</th>
                        <th className="r">Rating</th>
                        <th className="r" style={{width:90}}>Strength</th>
                        <th className="r">Δ Last</th>
                        <th className="r">Record</th>
                      </tr>
                    </thead>
                    <tbody>
                      {teams.map((team,i)=>{
                        const rank=i+1
                        const barPct=((team.rating-minRating)/(maxRating-minRating))*100
                        const chgPos=team.change>0
                        const teamColor=tc(team.abbr)
                        const secColor=ts(team.abbr)
                        // BRK has black primary so use tertiary grey; SA uses secondary silver
                        const fillColor = team.abbr==='BRK' ? tt(team.abbr) : teamColor
                        // Left-side gradient: full team color through rank+logo area, fades to transparent before data cols
                        const rowGradient=`linear-gradient(to right, ${fillColor} 0%, ${fillColor} 180px, ${fillColor}55 260px, transparent 340px)`
                        return(
                          <tr key={team.abbr} style={{
                            borderLeft:`4px solid ${fillColor}`,
                            background: rowGradient,
                            transition:'opacity 0.1s',
                          }}
                          onMouseEnter={e=>e.currentTarget.style.opacity='0.88'}
                          onMouseLeave={e=>e.currentTarget.style.opacity='1'}
                          >
                            {/* Rank */}
                            <td style={{textAlign:'right',padding:'0 10px 0 6px',fontFamily:mono,
                              fontSize:13,fontWeight:700,color:'#fff',width:36}}>{rank}</td>
                            {/* Team — name only, no conf/div */}
                            <td style={{padding:'10px 8px'}}>
                              <div style={{display:'flex',alignItems:'center',gap:10}}>
                                <div style={{width:34,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}>
                                  <TeamLogo abbr={team.abbr} size={28}/>
                                </div>
                                <div style={{fontSize:13,fontWeight:700,color:secColor,lineHeight:1.2}}>{team.name}</div>
                              </div>
                            </td>
                            {/* Rating */}
                            <td style={{textAlign:'right',padding:'0 16px',fontFamily:mono,fontSize:14,fontWeight:700,color:C.text,whiteSpace:'nowrap'}}>{team.rating.toFixed(1)}</td>
                            {/* Strength bar */}
                            <td style={{padding:'0 8px',width:130}}>
                              <div style={{height:4,background:'rgba(0,0,0,0.12)',borderRadius:2}}>
                                <div style={{width:`${barPct}%`,height:4,borderRadius:2,background:fillColor}}/>
                              </div>
                            </td>
                            {/* Delta — colored text on tinted bg */}
                            <td style={{textAlign:'right',padding:'0 12px',whiteSpace:'nowrap'}}>
                              <span style={{fontFamily:mono,fontSize:12,fontWeight:700,
                                padding:'2px 8px',borderRadius:4,display:'inline-block',
                                color:chgPos?'#1a7a34':'#b91c1c',
                                background:chgPos?'rgba(26,122,52,0.12)':'rgba(185,28,28,0.10)'}}>
                                {(chgPos?'+':'')+team.change.toFixed(1)}
                              </span>
                            </td>
                            {/* Record */}
                            <td style={{textAlign:'right',padding:'0 16px',fontFamily:mono,fontSize:12,fontWeight:500,color:C.text2,whiteSpace:'nowrap'}}>{team.w}–{team.l}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )
              }
            </div>
            <div className="right-col">
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:10,gap:8}}>
                <div className="section-label" style={{marginBottom:0}}>Games</div>
                {latestDate&&selectedDate!==latestDate&&(
                  <button onClick={()=>setSelectedDate(latestDate)} style={{
                    fontFamily:mono,fontSize:10,color:C.acc,background:'none',
                    border:`1px solid ${C.acc}40`,borderRadius:5,padding:'3px 8px',cursor:'pointer'}}>
                    Jump to latest
                  </button>
                )}
              </div>
              <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:14}}>
                <button onClick={()=>selectedDate&&setSelectedDate(shiftDate(selectedDate,-1))}
                  style={{fontFamily:mono,fontSize:13,color:C.text2,background:'#fff',
                    border:`1px solid ${C.border2}`,borderRadius:6,padding:'4px 9px',cursor:'pointer'}}>
                  ‹
                </button>
                <input type="date" value={selectedDate||''} onChange={e=>setSelectedDate(e.target.value)}
                  style={{fontFamily:mono,fontSize:12,color:C.text,background:'#fff',
                    border:`1px solid ${C.border2}`,borderRadius:6,padding:'4px 8px',flex:1}}/>
                <button onClick={()=>selectedDate&&setSelectedDate(shiftDate(selectedDate,1))}
                  style={{fontFamily:mono,fontSize:13,color:C.text2,background:'#fff',
                    border:`1px solid ${C.border2}`,borderRadius:6,padding:'4px 9px',cursor:'pointer'}}>
                  ›
                </button>
              </div>
              {dateLoading?(
                <div style={{color:C.text3,fontFamily:mono,fontSize:13,padding:'1.5rem 0',textAlign:'center'}}>Loading…</div>
              ):dateGames.length===0?(
                <div style={{color:C.text3,fontFamily:mono,fontSize:12,padding:'1.5rem 0',textAlign:'center',
                  border:`1px dashed ${C.border2}`,borderRadius:10}}>
                  No games on {selectedDate?formatDate(selectedDate):'this date'}
                </div>
              ):(
              <div className="games-list">
                {dateGames.map((g,i)=>{
                  const homeWon=g.homeScore>g.awayScore
                  const isPlayoff=g.type==='P'
                  const awayColor=tc(g.away)
                  const homeColor=tc(g.home)
                  const homeFav = g.winProb != null && g.winProb >= 0.5
                  const favPct  = g.winProb != null ? Math.round(homeFav ? g.winProb*100 : (1-g.winProb)*100) : null
                  return(
                    <div key={i} className="game-card">
                      {/* Meta row */}
                      <div className="game-meta">
                        <span className="game-date">{formatDate(g.date)}</span>
                        <span className={`game-round${isPlayoff?' playoff':''}`}>{roundLabel(g.round,g.type)}</span>
                      </div>

                      {/* Scoreboard — mirror layout */}
                      <div style={{display:'flex',alignItems:'center',padding:'12px 0 8px'}}>

                        {/* Away side — centered */}
                        <div style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',gap:3}}>
                          <span style={{fontFamily:mono,fontSize:12,fontWeight:400,
                            color:C.text2,letterSpacing:0.3}}>{g.away}</span>
                          <span style={{fontFamily:mono,fontSize:30,fontWeight:900,lineHeight:1,
                            color:homeWon?C.text:'#D4AF37',
                            textShadow:homeWon?'none':'0 0 14px rgba(212,175,55,0.55)',
                            paddingBottom:1}}>{g.awayScore}</span>
                          <span style={{fontFamily:mono,fontSize:10,color:C.text3}}>{g.awayRating?.toFixed(1)}</span>
                        </div>

                        {/* Away logo */}
                        <TeamLogo abbr={g.away} size={34} style={{flexShrink:0}}/>

                        {/* Center: OT pill + @ */}
                        <div style={{display:'flex',flexDirection:'column',alignItems:'center',
                          gap:3,padding:'0 8px',flexShrink:0,minWidth:44}}>
                          <span style={{fontFamily:mono,fontSize:9,fontWeight:700,
                            padding:'2px 5px',borderRadius:3,letterSpacing:0.5,
                            background:g.ot?'rgba(191,87,0,0.15)':'transparent',
                            color:g.ot?C.ut:'transparent',
                            border:g.ot?`1px solid rgba(191,87,0,0.25)`:'1px solid transparent',
                          }}>OT</span>
                          <span style={{fontFamily:mono,fontSize:10,color:C.text3,fontWeight:500}}>@</span>
                        </div>

                        {/* Home logo */}
                        <TeamLogo abbr={g.home} size={34} style={{flexShrink:0}}/>

                        {/* Home side — centered */}
                        <div style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',gap:3}}>
                          <span style={{fontFamily:mono,fontSize:12,fontWeight:400,
                            color:C.text2,letterSpacing:0.3}}>{g.home}</span>
                          <span style={{fontFamily:mono,fontSize:30,fontWeight:900,lineHeight:1,
                            color:homeWon?'#D4AF37':C.text,
                            textShadow:homeWon?'0 0 14px rgba(212,175,55,0.55)':'none',
                            paddingBottom:1}}>{g.homeScore}</span>
                          <span style={{fontFamily:mono,fontSize:10,color:C.text3}}>{g.homeRating?.toFixed(1)}</span>
                        </div>

                      </div>

                      {/* Impact row */}
                      <div className="game-impact" style={{borderTop:`1px solid ${C.border}`,marginTop:2,paddingTop:8}}>
                        <span className="impact-item">
                          {g.away} <strong className={g.awayChange>0?'pos':'neg'}>{g.awayChange>0?'+':''}{g.awayChange?.toFixed(1)}</strong>
                        </span>
                        {favPct!=null&&(
                          <span className="impact-item" style={{display:'flex',alignItems:'center',gap:3}}>
                            {!homeFav&&<span style={{color:C.acc,fontSize:10}}>◀</span>}
                            <strong style={{fontFamily:mono,fontSize:11,color:C.text2}}>{favPct}%</strong>
                            {homeFav&&<span style={{color:C.acc,fontSize:10}}>▶</span>}
                          </span>
                        )}
                        <span className="impact-item">
                          {g.home} <strong className={g.homeChange>0?'pos':'neg'}>{g.homeChange>0?'+':''}{g.homeChange?.toFixed(1)}</strong>
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
              )}
            </div>
          </div>
        )}

        {activeTab==='standings'&&(
          loading
            ?<div style={{color:C.text3,fontFamily:mono,fontSize:13,padding:'2rem 0'}}>Loading…</div>
            :<StandingsTab teams={teams} poGames={poGames}/>
        )}

        {activeTab==='bracket'&&(
          loading
            ?<div style={{color:C.text3,fontFamily:mono,fontSize:13,padding:'2rem 0'}}>Loading…</div>
            :<div style={{overflowX:'auto'}}><BracketTab poGames={poGames} teams={teams}/></div>
        )}
      </div>

      <Footer/>
    </div>
  )
}
