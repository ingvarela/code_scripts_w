case KeyCode.RIGHT: {
  const requestText = "Provide me 5 utterance recommendations";

  setIsChatOverlayVisible(true);
  setUserPrompt(requestText);

  const outgoingMessage: Messages = {
    ...NativeMessage,
    usr_request: requestText,
    sys_prompt: rightButtonSystemPrompt,
  };

  console.log("Sending RIGHT-button data:", outgoingMessage);

  OCR_Service.getOCRResponse(outgoingMessage).then((data) => {
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
  });

  break;
}