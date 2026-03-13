const submitUserPrompt = useCallback(async () => {
  console.log("submitUserPrompt:", NativeMessage.usr_request);

  const requestText = NativeMessage.usr_request.trim();
  if (!requestText) return;

  // Show only the newest request while waiting for the response
  showLatestRequestOnly(requestText);
  setUserPrompt("");

  const data = await OCR_Service.getOCRResponse(NativeMessage);

  const cleanedAnswer = data?.trim() || "";
  const finalAnswer = cleanedAnswer.toLowerCase().startsWith("answer:")
    ? cleanedAnswer.slice(7).trim()
    : cleanedAnswer;

  if (finalAnswer) {
    showLatestRequestAndResponse(requestText, finalAnswer);
    setQwenAnswer(finalAnswer);
  } else {
    setQwenAnswer("");
  }
}, [
  NativeMessage,
  showLatestRequestOnly,
  showLatestRequestAndResponse,
]);