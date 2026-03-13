const submitUserPrompt = useCallback(async () => {
  console.log("submitUserPrompt:", NativeMessage.usr_request);

  const requestText = NativeMessage.usr_request.trim();
  if (!requestText) return;

  // Show only the newest request while waiting for the response
  showLatestRequestOnly(requestText);
  setUserPrompt("");

  const assistantResponse = await sendMessagesToSDSA(NativeMessage);

  if (assistantResponse) {
    // Replace everything with only the latest request + latest response
    showLatestRequestAndResponse(requestText, assistantResponse);

    if (typeof assistantResponse === "string") {
      setQwenAnswer(assistantResponse);
    }
  } else {
    setQwenAnswer("");
  }
}, [
  NativeMessage,
  sendMessagesToSDSA,
  showLatestRequestOnly,
  showLatestRequestAndResponse,
]);