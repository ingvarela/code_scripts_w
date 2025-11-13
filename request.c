const fs = require("fs")
const http = require("http")

async function process_prompt() {
  const query = {
    filename: "test.jpg",
    full_query: `<|im_start|>system
You are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>
<|im_start|>user
<image>
Describe the objects in the room in a few sentences.<|im_end|>
<|im_start|>assistant
`
  }

  let reqId = 0

  const imageBase64 = fs.readFileSync(query.filename, "base64")

  let prompt_str = query.full_query

  console.log(prompt_str)

  const postDataJson = {
    purpose: "vlm",
    query: prompt_str,
    image: imageBase64,
    reqid: reqId
  };

  const postData = Buffer.from(JSON.stringify(postDataJson))

  const result = await new Promise((resolve) => {
    const req = http.request({
      hostname: "192.168.3.80",
      path: "/generate",
      port: 9090,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": postData.byteLength
      }
    }, (res) => {
      const chunks = []

      res.on("data", (chunk) => {
        chunks.push(chunk)
      })

      res.on("end", () => {
        const concat = Buffer.concat(chunks).toString("utf8")
        const json = JSON.parse(concat)

        resolve(json)
      })
    })

    req.write(postData)
    req.end()
  })

  console.log(result)
}

process_prompt()
