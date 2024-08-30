use cloudevents::binding::reqwest::RequestBuilderExt;
use cloudevents::binding::warp::{filter, reply};
use cloudevents::{AttributesReader, AttributesWriter, Event};
use std::{cell::RefCell, env, fs, thread, time};
use tokio::task::JoinHandle;
use warp::Filter;

static FAN_OUT_SCALE: u32 = 5;
thread_local! {
    static S3_COUNTER: RefCell<u32> = const { RefCell::new(0) };
}

// We must wait for the POST event to go through before we can return, as
// otherwise the chain may not make progress
pub fn post_event(dest: String, event: Event) -> JoinHandle<()> {
    tokio::spawn(async {
        reqwest::Client::new()
            .post(dest)
            .event(event)
            .map_err(|e| e.to_string())
            .unwrap()
            .header("Access-Control-Allow-Origin", "*")
            .send()
            .await
            .map_err(|e| e.to_string())
            .unwrap();
    })
}

// This function is a general wrapper that takes a cloud event as an input,
// decides what function to execute, and outputs another cloud event
pub fn process_event(mut event: Event) -> Event {
    // -----
    // Pre-process and function invocation
    // -----

    event.set_source(match event.source().as_str() {
        "cli" => {
            println!("cloudevent: executing step-one from cli: {event}");

            // Simulate actual function execution by a sleep
            thread::sleep(time::Duration::from_millis(3000));

            "step-one"
        }
        "step-one" => {
            println!("cloudevent: executing step-two from step-one: {event}");

            // Simulate actual function execution by a sleep
            thread::sleep(time::Duration::from_millis(10000));

            "step-two"
        }
        "step-two" => {
            println!("cloudevent: executing step-three from step-two: {event}");

            // Simulate actual function execution by a sleep
            thread::sleep(time::Duration::from_millis(500));

            S3_COUNTER.with(|counter| {
                *counter.borrow_mut() += 1;
                println!(
                    "cloudevent(s3): counted {}/{}",
                    counter.borrow(),
                    FAN_OUT_SCALE
                );

                if *counter.borrow() == FAN_OUT_SCALE {
                    println!("cloudevent(s3): done!");
                }
            });

            "step-three"
        }
        _ => panic!(
            "cloudevent: error: unrecognised source: {:}",
            event.source()
        ),
    });

    // -----
    // Post-process
    // -----

    match event.source().as_str() {
        "step-one" => {
            // Store the destinattion channel
            let dst = event.ty();

            let mut scaled_event = event.clone();

            // Write the new destination channel
            // FIXME: this is hardcoded in chaining.yaml
            scaled_event.set_type("http://two-to-three-kn-channel.chaining-test.svc.cluster.local");

            println!("cloudevent(s1): fanning out by a factor of {FAN_OUT_SCALE}");

            for i in 1..FAN_OUT_SCALE {
                scaled_event.set_id(i.to_string());

                println!(
                    "cloudevent(s1): posting to {dst} event {i}/{FAN_OUT_SCALE}: {scaled_event}"
                );
                post_event(dst.to_string(), scaled_event.clone());
            }

            // Return the last event through the HTTP respnse
            scaled_event.set_id("0");
            scaled_event
        }
        "step-two" => {
            // We still need to POST the event manually but we need to do
            // it outside this method to be able to await on it (this method,
            // itself, is being await-ed on when called in a server loop)

            event
        }
        "step-three" => {
            // Nothing to do after "step-three" as it is the last step in the chain

            event
        }
        _ => panic!(
            "cloudevent: error: unrecognised destination: {:}",
            event.source()
        ),
    }
}

#[tokio::main]
async fn main() {
    match env::var("CE_FROM_FILE") {
        Ok(value) => {
            assert!(value == "on");

            // This filepath is hard-coded in the JobSink specification:
            // https://knative.dev/docs/eventing/sinks/job-sink
            let file_contents = fs::read_to_string("/etc/jobsink-event/event").unwrap();
            let json_value = serde_json::from_str(&file_contents).unwrap();
            let event: Event = serde_json::from_value(json_value).unwrap();

            let processed_event = process_event(event);

            // After executing step-two, we just need to post a clone of the
            // event to the type (i.e. destination) provided in it. Given that
            // step-two runs in a JobSink, the pod will terminate on exit, so
            // we need to make sure that the POST is sent before we move on
            println!(
                "cloudevent(s2): posting to {} event: {processed_event}",
                processed_event.ty()
            );
            post_event(processed_event.ty().to_string(), processed_event.clone())
                .await
                .unwrap();
        }
        Err(env::VarError::NotPresent) => {
            let routes = warp::any()
                // Extract event from request
                .and(filter::to_event())
                // Return the post-processed event
                .map(|event| reply::from_event(process_event(event)));

            warp::serve(routes).run(([127, 0, 0, 1], 8080)).await;
        }
        Err(e) => println!("Failed to read env. var: {}", e),
    };
}
