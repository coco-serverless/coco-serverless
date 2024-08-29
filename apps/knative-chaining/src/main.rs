use cloudevents::binding::reqwest::RequestBuilderExt;
use cloudevents::binding::warp::{filter, reply};
use cloudevents::{AttributesReader, AttributesWriter, Event};
use std::{cell::RefCell, env, fs, thread, time};
use warp::reply::Response;
use warp::Filter;

static FAN_OUT_SCALE: u32 = 5;
thread_local! {
    static S3_COUNTER: RefCell<u32> = RefCell::new(0);
}

pub fn post_event(dest: String, event: Event) {
    // WARNING: we use the type to attribute to indicate the
    // reply-to attribute
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
    });
}

// This function is a general wrapper that takes a cloud event as an input,
// decides what function to execute, and outputs another cloud event
pub fn process_event(mut event: Event) -> Response {
    // Here we need to enforce the structure of our DAG:
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
            println!("cloudevent: executing step-two from step-one: {event}");

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

    // Post-process based on new source (i.e. current function)
    match event.source().as_str() {
        "step-one" => {
            // Store the destinattion channel
            let dst = event.ty();

            let mut scaled_event = event.clone();

            // Write the new destination channel
            // FIXME: this is hardcoded in chaining.yaml
            scaled_event.set_type("http://two-to-three-kn-channel.chaining-test-svc.cluster.local");

            println!("step-two: fanning out by a factor of {FAN_OUT_SCALE}");

            for i in 1..FAN_OUT_SCALE {
                scaled_event.set_id(i.to_string());

                println!("Posting to {dst} event {i}/{FAN_OUT_SCALE}: {scaled_event}");
                post_event(dst.to_string(), scaled_event.clone());
            }

            // Return the last event through the HTTP respnse
            scaled_event.set_id("0");
            return reply::from_event(scaled_event);
        }
        "step-two" => {
            // After executing step-two, we just need to post a clone of the
            // event to the type (i.e. destination) provided in it
            post_event(event.ty().to_string(), event.clone());

            // FIXME: we return here but we know that we ignore the return
            // value because step-two is a JobSink, and hence not invoked
            // through HTTP. In the future we should make the function allow
            // different types of return values
            return reply::from_event(event);
        }
        _ => panic!(
            "cloudevent: error: unrecognised destination: {:}",
            event.source()
        ),
    };
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

            // FIXME: process_event returns an HTTP response. Naturally, when
            // reading a CloudEvent from a file we have no-where to respond
            // it to.
            process_event(event);
        }
        Err(env::VarError::NotPresent) => {
            let routes = warp::any()
                // Extract event from request
                .and(filter::to_event())
                // Return the post-processed event
                .map(process_event);

            warp::serve(routes).run(([127, 0, 0, 1], 8080)).await;
        }
        Err(e) => println!("Failed to read env. var: {}", e),
    };
}
