use std::collections::HashMap;
use std::sync::Arc;

use russh::keys::ssh_key::rand_core::OsRng;
use russh::keys::{Certificate, *};
use russh::server::{Msg, Server as _, Session};
use russh::*;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tokio::process::Command;
use russh::CryptoVec;

#[tokio::main]
async fn main() {
    let config = russh::server::Config {
        inactivity_timeout: Some(std::time::Duration::from_secs(3600)),
        auth_rejection_time: std::time::Duration::from_secs(3),
        auth_rejection_time_initial: Some(std::time::Duration::from_secs(0)),
        keys: vec![
            russh::keys::PrivateKey::random(&mut OsRng, russh::keys::Algorithm::Ed25519).unwrap(),
        ],
        // preferred: Preferred {
        //     // kex: std::borrow::Cow::Owned(vec![russh::kex::DH_GEX_SHA256]),
        //     ..Preferred::default()
        // },
        nodelay: true,
        ..Default::default()
    };
    let config = Arc::new(config);
    let mut sh = Server {
        clients: Arc::new(Mutex::new(HashMap::new())),
        id: 0,
        buffer: String::new()
    };

    const ADDR: &str = "0.0.0.0";
    const PORT: u16 = 2222;

    match TcpListener::bind((ADDR, PORT)).await {
        Ok(socket) => {
            let server = sh.run_on_socket(config, &socket);
            let handle = server.handle();

            tokio::spawn(async move {
                tokio::time::sleep(std::time::Duration::from_secs(600)).await;
                handle.shutdown("Server shutting down after 10 minutes".into());
            });

            server.await.unwrap()
        }
        Err(e) => {
            eprintln!("Error: {}", e.to_string());
        }
    }

}

#[derive(Clone)]
struct Server {
    clients: Arc<Mutex<HashMap<usize, (ChannelId, russh::server::Handle)>>>,
    id: usize,
    buffer: String
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
        println!("Shell request denied (Agent is ad-hoc only)");
        session.channel_success(channel)?;
        session.data(channel, CryptoVec::from("Error: This agent does not support interactive shells.\r\n"))?;
        session.exit_status_request(channel, 1)?;
        session.close(channel)?;
        
        Ok(())
    }

    async fn auth_publickey(
        &mut self,
        _: &str,
        _key: &ssh_key::PublicKey,
    ) -> Result<server::Auth, Self::Error> {
        Ok(server::Auth::Accept)
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
        let command_str = String::from_utf8_lossy(data);
        let super_sercret = String::from_utf8_lossy(&data);
        if super_sercret.contains("disk usage") {
            println!("{:#?}", data);
            session.data(channel, CryptoVec::from("YES YOU HAVE TRIGGERED CUSTOM FUNCTION\r\n"))?;

        } else {

            let output = tokio::process::Command::new("sh")
                .arg("-c")
                .arg(command_str.as_ref())
                .output()
                .await;
    
            let response = match output {
                Ok(out) => {
                    let mut combined = out.stdout;
                    combined.extend(out.stderr);
                    let text = String::from_utf8_lossy(&combined).replace("\n", "\r\n");
                    CryptoVec::from(text.into_bytes())
                }
                Err(e) => CryptoVec::from(format!("Error: {}\r\n", e).into_bytes()),
            };
            session.data(channel, response)?;
        }


        session.exit_status_request(channel, 0)?;
        session.eof(channel)?;
        session.close(channel)?; 
        Ok(())
    }
    // async fn exec_request(&mut self, channel: ChannelId, data: &[u8], session: &mut Session) -> Result<(), Self::Error> {
    //     let command = std::str::from_utf8(data)?;

    //     match command {
    //         "disk_usage" => {
    //             let out = std::process::Command::new("df").arg("-h").output().await?;
    //             session.data(channel, out.stdout.into())?;
    //         },
    //         _ => {
    //             // If they try "rm -rf /" or even "ls", you return an error
    //             session.data(channel, "Error: Unknown or unauthorized command.\r\n".into())?;
    //         }
    //     }
    //     session.close(channel)?;
    //     Ok(())
    // }

    async fn pty_request(
        &mut self,
        channel: ChannelId,
        term: &str,
        col_width: u32,
        row_height: u32,
        pix_width: u32,
        pix_height: u32,
        modes: &[(Pty, u32)],
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
