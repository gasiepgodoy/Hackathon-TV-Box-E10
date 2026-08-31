use msedge_tts::{tts::client::TtsClient, tts::client::TtsClientBuilder};
use std::env;
use std::fs::File;
use std::io::Write;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Uso: {} <texto> [voice] [pitch] [rate] [output_file]", args[0]);
        std::process::exit(1);
    }

    let text = &args[1];
    let voice = args.get(2).map(|s| s.as_str()).unwrap_or("pt-BR-FranciscaNeural");
    let out_file = args.get(5).map(|s| s.as_str()).unwrap_or("output.mp3");

    let mut client = TtsClient::connect().await?;
    let audio_data = client.speak_all(text, voice).await?;

    let mut file = File::create(out_file)?;
    file.write_all(&audio_data)?;

    println!("OK");
    Ok(())
}
