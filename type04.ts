<div
  ref={chatRef}
  style={{
    position: "absolute",
    top: "2%",
    right: "1%",
    width: "27%",
    height: "56%",
    maxHeight: "56%",
    backgroundColor: "rgba(0, 0, 0, 0.65)",
    color: "white",
    fontSize: "30px",
    boxShadow: "0 4px 6px rgba(0, 0, 0, 0.1)",
    fontFamily: "'Samsung Sans', Arial, sans-serif",
    clipPath: `polygon(
      0 5%,
      5% 0,
      100% 0,
      100% 95%,
      95% 100%,
      0% 100%
    )`,
    boxSizing: "border-box",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  }}
>