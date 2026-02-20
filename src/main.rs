use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;

use russh::keys::*;
use russh::server::{Msg, Server as _, Session};
use russh::*;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tokio::process::Command;
use clap::Parser;
use russh::CryptoVec;
use sysinfo::System;



#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    let system_facts = get_gathered_system_facts();
    println!("{}", system_facts.long_os_name);
    const DIVIDER: u64 = 1073741824;
    println!("{:.2} GiB", system_facts.total_ram_in_bytes as f64 /  DIVIDER as f64);
    
    let key_data = fs::read_to_string(cli.private_key).map_err(|e| format!("Please provide a valid private key file: {}", e))?;
    let private_key = PrivateKey::from_openssh(&key_data).map_err(|e| format!("Invalid host key format: {}", e))?;
    

    let config = russh::server::Config {
        inactivity_timeout: Some(std::time::Duration::from_secs(3600)),
        auth_rejection_time: std::time::Duration::from_secs(3),
        auth_rejection_time_initial: Some(std::time::Duration::from_secs(0)),
        keys: vec![private_key],
        ..Default::default()
    };

    let config = Arc::new(config);
    let mut sh: Server = Server {
        system_facts: Arc::new(system_facts),
        clients: Arc::new(Mutex::new(HashMap::new())),
        id: 0,
        // buffer: String::new()
    };

    const ADDR: &str = "0.0.0.0";
    let socket = TcpListener::bind((ADDR, cli.port)).await?;

    let server = sh.run_on_socket(config, &socket);
    let handle = server.handle();

    tokio::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_secs(600)).await;
        handle.shutdown("Server shutting down after 10 minutes".into());
    });
    println!("Server listening on {}:{}", ADDR, cli.port);
    server.await?;
    
    Ok(())

}

#[derive(Clone)]
struct Server {
    system_facts: Arc<SystemFacts>,
    clients: Arc<Mutex<HashMap<usize, (ChannelId, russh::server::Handle)>>>,
    id: usize,
    // buffer: String
}

struct SystemFacts {
    long_os_name: String,
    total_ram_in_bytes: u64
}

impl server::Server for Server {
    type Handler = Self;
    fn new_client(&mut self, _: Option<std::net::SocketAddr>) -> Self {
        let s = self.clone();
        self.id += 1;
        s
    }
    fn handle_session_error(&mut self, _error: <Self::Handler as russh::server::Handler>::Error) {
        eprintln!("Session error: {_error:#?}");
    }
}

impl server::Handler for Server {
    type Error = russh::Error;

    async fn channel_open_session(
        &mut self,
        channel: Channel<Msg>,
        session: &mut Session,
    ) -> Result<bool, Self::Error> {
        {
            let mut clients = self.clients.lock().await;
            clients.insert(self.id, (channel.id(), session.handle()));
        }
        Ok(true)
    }

    async fn shell_request(
        &mut self,
        channel: ChannelId,
        session: &mut Session,
    ) -> Result<(), Self::Error> {
        println!("Shell request denied for channel id {}.", channel);
        session.channel_success(channel)?;
        session.data(channel, CryptoVec::from("Error: Interactive shells are not supported.\r\n"))?;
        session.exit_status_request(channel, 1)?;
        session.close(channel)?;
        
        Ok(())
    }

    async fn auth_publickey(
        &mut self,
        user: &str,
        _key: &ssh_key::PublicKey,
    ) -> Result<server::Auth, Self::Error> {
        println!("Public key of the user \"{}\" was accepted.", user);
        Ok(server::Auth::Accept)
        // TODO: proper allowence for admin (central point)
    }

    // // Inside your russh server handler
    // async fn auth_publickey(&mut self, user: &str, key: &russh::keys::PublicKey) -> Result<Auth, Self::Error> {
    //     // Only allow the user 'orchestrator' with a SPECIFIC key fingerprint
    //     if user == "orchestrator" && key.fingerprint() == "SHA256:your_central_point_key_here" {
    //         Ok(Auth::Accept)
    //     } else {
    //         Ok(Auth::Reject) // Everyone else is kicked out here
    //     }
    // }

    async fn exec_request(
        &mut self,
        channel: ChannelId,
        data: &[u8], // This contains the command string
        session: &mut Session,
    ) -> Result<(), Self::Error> {
        session.channel_success(channel)?; // Acknowledge the request
        let command = std::str::from_utf8(data)?;

        match command {
            "disk usage" => {
                session.data(channel, CryptoVec::from(format!("{}\r\n", self.system_facts.long_os_name)))?;

            }
            _ => {
                session.data(channel, "Error: Unauthorized command.\r\n".into())?;
                
            }
        }


        session.exit_status_request(channel, 0)?;
        session.eof(channel)?;
        session.close(channel)?; 
        Ok(())
    }

    async fn pty_request(
        &mut self,
        channel: ChannelId,
        _term: &str,
        _col_width: u32,
        _row_height: u32,
        _pix_width: u32,
        _pix_height: u32,
        _modes: &[(Pty, u32)],
        session: &mut Session,
    ) -> Result<(), Self::Error> {
        session.channel_success(channel)?; 
        Ok(())
    }

// ➜  server git:(server) ✗ ssh-keygen -f '/home/andrey/.ssh/known_hosts' -R '[localhost]:2222' && ssh -p 2222 -nNf -MS /tmp/mcp-socket localhost

// # Host [localhost]:2222 found: line 4
// /home/andrey/.ssh/known_hosts updated.
// Original contents retained as /home/andrey/.ssh/known_hosts.old
// The authenticity of host '[localhost]:2222 ([127.0.0.1]:2222)' can't be established.
// ED25519 key fingerprint is SHA256:kj5fhV+4BP3HIzTnrDtzLCPSI3xraqPqseLAIQFsZ7o.
// This key is not known by any other names.
// Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
// Warning: Permanently added '[localhost]:2222' (ED25519) to the list of known hosts.
// ➜  server git:(server) ✗ ssh -S /tmp/mcp-socket localhost "disk usage"
// ssh -S /tmp/mcp-socket localhost "whoami"
// YES YOU HAVE TRIGGERED CUSTOM FUNCTION
// andrey
// ➜  server git:(server) ✗ ssh -S /tmp/mcp-socket -O exit localhost
// Exit request sent.
// ➜  server git:(server) ✗



    // async fn data(
    //     &mut self,
    //     channel: ChannelId,
    //     data: &[u8],
    //     session: &mut Session,
    // ) -> Result<(), Self::Error> {
    //     for &byte in data {
    //         if byte == b'\r' || byte == b'\n' {
    //             let received_cmd = self.buffer.trim();
                
    //             let received_cmd_output = Command::new("sh").arg("-c").arg(received_cmd).output().await;

    //             session.data(channel, CryptoVec::from(&b"\r\n"[..]))?;

    //             match received_cmd_output {
    //                 Ok(output) => {
    //                     let display_bytes = if !output.stdout.is_empty() {
    //                         &output.stdout
    //                     } else {
    //                         &output.stderr
    //                     };
    //                     let formatted = String::from_utf8_lossy(display_bytes).replace("\n", "\r\n");
    //                     session.data(channel, CryptoVec::from(formatted))?;
    //                 }
    //                 Err(e) => {
    //                     session.data(channel, CryptoVec::from(format!("Error: {}\r\n", e)))?;
    //                 }
    //             }

    //             session.data(channel, CryptoVec::from(&b"rust-shell> "[..]))?;

    //             self.buffer.clear();
    //         } else if byte == 127 {
    //             self.buffer.pop();
    //             session.data(channel, CryptoVec::from(&b"\x08 \x08"[..]))?;
    //         } else if byte == 3 {
    //             session.data(channel, CryptoVec::from(&b"logout\r\n"[..]))?;
    //             return Err(russh::Error::Disconnect);
    //         } else {
    //             self.buffer.push(byte as char);
    //             session.data(channel, CryptoVec::from(&[byte][..]))?;
    //         }
    //     }

    //     Ok(())
    // }

}

fn get_gathered_system_facts() -> SystemFacts{
    let mut sys = System::new();
    let long_os_name = System::long_os_version().unwrap_or_else(|| "<unknown>".to_owned());
    sys.refresh_memory(); 

    SystemFacts {
        long_os_name: long_os_name,
        total_ram_in_bytes: sys.total_memory()
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        let id = self.id;
        let clients = self.clients.clone();
        tokio::spawn(async move {
            let mut clients = clients.lock().await;
            clients.remove(&id);
        });
    }
}

#[derive(Parser, Debug)]
#[command(long_about = None)]
pub struct Cli {
    #[clap(long, short = 'P', default_value_t = 2222)]
    port: u16,

    #[clap(long, short = 'p', required = true)]
    private_key: PathBuf,
}