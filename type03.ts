case KeyCode.RIGHT: {
  const requestText = "Whats on TV";

  setIsChatOverlayVisible(true);
  setUserPrompt(requestText);

  const outgoingMessage: Messages = {
    ...NativeMessage,
    usr_request: requestText,
  };

  // Immediately replace old request/response with the new request
  showLatestRequestOnly(requestText);
  console.log("Sending Data:", outgoingMessage);

  const assistantResponse = await sendMessagesToSDSA(outgoingMessage);

  if (assistantResponse) {
    // Show only the newest request and its response
    showLatestRequestAndResponse(requestText, assistantResponse);

    if (typeof assistantResponse === "string") {
      setQwenAnswer(assistantResponse);
    }
  } else {
    setQwenAnswer("");
  }

  break;
}