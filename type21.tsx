const submitUserPrompt = useCallback(async () => {
  console.log("submitUserPrompt:", NativeMessage.usr_request);

  const requestText = NativeMessage.usr_request.trim();
  if (!requestText) return;

  // Show only the newest request in ChatOverlay
  showLatestRequestOnly(requestText);

  setUserPrompt("");
  setQwenAnswer(""); // clear previous answer while loading the new one

  const data = await OCR_Service.getOCRResponse(NativeMessage);

  const cleanedAnswer = data?.trim() || "";
  const finalAnswer = cleanedAnswer.toLowerCase().startsWith("answer:")
    ? cleanedAnswer.slice(7).trim()
    : cleanedAnswer;

  if (finalAnswer) {
    // Only update MockAnswerDisplay
    setQwenAnswer(finalAnswer);
  } else {
    setQwenAnswer("");
  }
}, [
  NativeMessage,
  showLatestRequestOnly,
]);