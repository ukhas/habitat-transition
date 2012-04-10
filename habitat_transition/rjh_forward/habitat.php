<?php
require_once "JSON.php";

/*
 * habitat($_POST["identity"], $_POST["string"])
 * e.g., habitat("DANIEL", "hello world from php!");
 *       habitat("DANIEL", "ZC,Daniel_Chase_Car,51.4567,0.1529,123");
 *       habitat("DANIEL", "ZZ,DANIEL,2011-08-12 21:44:30,51.4,0.5,".
 *                         "Yaesu FT817ND,Yagi,r400,A1");
 */

/* $habitat_url = "http://localhost:5000/%s"; */
$habitat_url = "http://habitat.habhub.org/transition/%s";

function habitat($identity, $string)
{
    $string = trim($string);
    $t = substr($string, 0, 3);

    switch (substr($string, 0, 3))
    {
        case "ZZ,":
            habitat_zz($string);
            break;

        case "ZC,":
            habitat_zc($string);
            break;

        default:
            habitat_string($identity, $string);
            break;
    }
}

function habitat_string($identity, $string)
{
    $string = '$$'.$string."\n";

    $callsign = habitat_callsign($identity);
    $metadata = array();

    habitat_payload_telemetry($callsign, $string, $metadata);
}

function habitat_zz($string)
{
    /* ZZ,CALLSIGN,YYYY-MM-DD HH:MM:SS,LAT (DD),LON (DD),RADIO,ANTENNA,
       VERSION,TRACKING-PAYLOAD */
    $parts = explode(",", $string);

    if (count($parts) != 9)
        return false;

    $callsign = habitat_callsign($parts[1]);

    $info_data = array(
        "radio" => (string) $parts[5],
        "antenna" => (string) $parts[6],
        "dl-fldigi" => array(
            "version" => (string) $parts[7],
            "payload" => (string) $parts[8]
        )
    );

    $datetime_parts = explode(" ", $parts[2]);
    $time_parts = habitat_split_time_string($datetime_parts[1]);

    $telemetry_data = array(
        "time" => $time_parts,
        "latitude" => (double) $parts[3],
        "longitude" => (double) $parts[4],
        "altitude" => 0
    );

    habitat_listener_info($callsign, $info_data);
    habitat_listener_telemetry($callsign, $telemetry_data);
}

function habitat_zc($string)
{
    /* ZC,chase_car,53.604408,-2.451177,155 */
    $parts = explode(",", $string);

    $callsign = habitat_callsign($parts[1]);

    if (count($parts) != 5)
        return false;

    $data = array(
        "time" => habitat_split_time_posix(time()),
        "latitude" => (double) $parts[2],
        "longitude" => (double) $parts[3],
        "altitude" => (int) $parts[4]
    );

    habitat_listener_telemetry($callsign, $data);
}

function habitat_callsign($callsign)
{
    /* If restrictions are added, this function might be required */
    return (string) $callsign;
}

function habitat_split_time_string($time_string)
{
    $time_parts = explode(":", $time_string);
    return array(
        "hour" => (int) $time_parts[0],
        "minute" => (int) $time_parts[1],
        "second" => (int) $time_parts[2]
    );
}

function habitat_split_time_posix($time)
{
    return array(
        "hour" => idate("H", $time),
        "minute" => idate("i", $time),
        "second" => idate("s", $time)
    );
}

function habitat_payload_telemetry($callsign, $string, $metadata)
{
    $json = new Services_JSON();

    $post_data = array(
        "callsign" => $callsign,
        "string" => base64_encode($string),
        "string_type" => "base64",
        "metadata" => $json->encode($metadata)
    );
    habitat_flask("payload_telemetry", $post_data);
}

function habitat_listener_info($callsign, $data)
{
    $json = new Services_JSON();

    $post_data = array(
        "callsign" => $callsign,
        "data" => $json->encode($data)
    );
    habitat_flask("listener_info", $post_data);
}

function habitat_listener_telemetry($callsign, $data)
{
    $json = new Services_JSON();

    $post_data = array(
        "callsign" => $callsign,
        "data" => $json->encode($data)
    );
    habitat_flask("listener_telemetry", $post_data);
}

function habitat_flask($type, $post_data)
{
    global $DEBUG_LEVEL;
    global $habitat_url;

    $post_data = http_build_query($post_data);

    if($DEBUG_LEVEL >= 2)
        echo '<strong>submitting to habitat:</strong>'.
             '<pre>'.htmlspecialchars($post_data).'</pre>';

    $url = sprintf($habitat_url, $type);
    $params = array(
        'http' => array(
            'method' => 'POST',
            'content' => $post_data,
            'header' => "Content-type: application/x-www-form-urlencoded\r\n"
        )
    );

    $ctx = stream_context_create($params);
    $fp = @fopen($url, 'rb', false, $ctx);

    if ($fp)
    {
        $resp = stream_get_contents($fp);

        if ($DEBUG_LEVEL >= 2)
        {
            echo '<strong>response from posting to habitat:</strong>'.
                 '<pre>'.htmlspecialchars($resp).'</pre>';
        }

        fclose($fp);
    }
    else
    {
        if ($DEBUG_LEVEL >= 2)
            echo '<strong>error opening connection to habitat!</strong>';
    }

    if ($DEBUG_LEVEL >= 2)
        echo "<br /><br />";
}
?>
