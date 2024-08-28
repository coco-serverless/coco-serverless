use cloudevents::{AttributesReader, AttributesWriter, Event};
use cloudevents::binding::warp::{filter, reply};
use serde_json::Value;
use warp::Filter;
use warp::reply::Response;

// This function is a general wrapper that takes a cloud event as an input,
// decides what function to execute, and outputs another cloud event
pub fn process_event(mut event: Event) -> Response {
    println!("source: {}", event.source());
    println!("event: {:?}", event.data());
    let (datacontenttype, _dataschema, data) = event.take_data();

    // TODO: do some pattern-matching depending on the cloud event's source
    // and type

    // Here we need to enforce the structure of our DAG:
    event.set_source(match event.source().as_str() {
        "cli" => {
            println!("HELLO: we are executing step-one from cli");
            "step-one"
        },
        "step-one" => {
            println!("HELLO: we are executing step-two from cli");
            "step-two"
        },
        _ => panic!("error: unrecognised source: {:}", event.source()),
    });

//     println!("data content: {}", datacontenttype.unwrap());
//     let actual_payload: Value = data.unwrap().try_into().unwrap();
//     println!("payload: {}", actual_payload);
//
//     let mut new_payload = actual_payload.clone();
//     new_payload["hello"] = "madafaka".try_into().unwrap();
//
//     event.set_data(
//         "application/json",
//         new_payload,
//     );

    reply::from_event(event)
}

#[tokio::main]
async fn main() {
    let routes = warp::any()
        // Extract event from request
        .and(filter::to_event())
        // Return the post-processed event
        .map(|event| process_event(event));

    warp::serve(routes).run(([127, 0, 0, 1], 8080)).await;
}
