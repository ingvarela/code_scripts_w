{shouldShowTextInProgress && (
  <div
    key={messages.length + 1}
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "10px",
      paddingLeft: "10px",
      paddingRight: "10px",
      paddingTop: "6px",
      paddingBottom: "6px",
      color: "gray",
      borderBottom: "solid 1px gray",
      boxSizing: "border-box",
      lineHeight: 1.2,
    }}
  >
    <div
      style={{
        flex: 1,
        minWidth: 0,
        wordBreak: "break-word",
        overflowWrap: "anywhere",
      }}
    >
      {textInProgress}
    </div>

    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <MicrophoneIcon isEnabled={isSpeechEnabled} />
    </div>
  </div>
)}