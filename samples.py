case KeyCode.RIGHT: {
  const requestText = "Provide me 5 utterance recommendations";

  setIsChatOverlayVisible(true);

  // Show the request directly without triggering the normal prompt pipeline
  showLatestRequestOnly(requestText);

  const outgoingMessage: Messages = {
    ...NativeMessage,
    usr_request: requestText,
    sys_prompt: rightButtonSystemPrompt,
  };

  console.log("Sending RIGHT-button data:", outgoingMessage);

  const data = await OCR_Service.getOCRResponse(outgoingMessage);

  console.log("ANSWER:");

  const cleanedAnswer = data?.trim() || "";
  const finalAnswer = cleanedAnswer.toLowerCase().startsWith("answer:")
    ? cleanedAnswer.slice(7).trim()
    : cleanedAnswer;

  if (finalAnswer) {
    setQwenAnswer(finalAnswer);
  } else {
    setQwenAnswer("");
  }

  break;
}