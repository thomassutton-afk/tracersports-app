import TeamPage from "./TeamPage";

export async function generateStaticParams() {
  const teams = [
    "atl","bos","brk","cha","chi","cle","dal","den","det","gs",
    "hou","ind","lac","lal","mem","mia","mil","min","no","ny",
    "okc","orl","phi","phx","por","sa","sac","tor","uta","was",
  ];
  return teams.map(abbr => ({ abbr }));
}

export async function generateMetadata({ params }) {
  const { abbr } = await params;
  const TEAM_NAMES = {
    atl:"Atlanta Hawks",         bos:"Boston Celtics",          brk:"Brooklyn Nets",
    cha:"Charlotte Hornets",     chi:"Chicago Bulls",            cle:"Cleveland Cavaliers",
    dal:"Dallas Mavericks",      den:"Denver Nuggets",           det:"Detroit Pistons",
    gs:"Golden State Warriors",  hou:"Houston Rockets",          ind:"Indiana Pacers",
    lac:"LA Clippers",           lal:"Los Angeles Lakers",       mem:"Memphis Grizzlies",
    mia:"Miami Heat",            mil:"Milwaukee Bucks",          min:"Minnesota Timberwolves",
    no:"New Orleans Pelicans",   ny:"New York Knicks",           okc:"Oklahoma City Thunder",
    orl:"Orlando Magic",         phi:"Philadelphia 76ers",       phx:"Phoenix Suns",
    por:"Portland Trail Blazers",sa:"San Antonio Spurs",         sac:"Sacramento Kings",
    tor:"Toronto Raptors",       uta:"Utah Jazz",                was:"Washington Wizards",
  };
  const name = TEAM_NAMES[abbr.toLowerCase()] || abbr.toUpperCase();
  return {
    title: `${name} | TRACER Sports`,
    description: `All-time TRACER power rating history for the ${name} — 30 seasons of franchise ratings, records, and playoff results.`,
  };
}

export default async function Page({ params }) {
  const { abbr } = await params;
  return <TeamPage abbr={abbr.toUpperCase()} />;
}