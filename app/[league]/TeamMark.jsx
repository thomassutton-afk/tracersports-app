export default function TeamMark({ team, size = 28 }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: team.primary,
        color: team.secondary === "#FFFFFF" || team.secondary === "#fff" ? team.secondary : "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--font-mono)",
        fontSize: size * 0.36,
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      {team.nickname ? team.nickname.slice(0, 2).toUpperCase() : "??"}
    </div>
  );
}
