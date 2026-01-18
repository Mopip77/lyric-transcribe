#!/usr/bin/env python
"""Test SSE endpoint with a real HTTP client."""

import asyncio
import aiohttp
import sys


async def test_sse():
    """Test SSE connection and event flow."""
    base_url = "http://localhost:8000"

    print("Testing SSE endpoint...")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # Check if server is running
        try:
            async with session.get(f"{base_url}/api/config") as resp:
                if resp.status != 200:
                    print(f"Server not responding properly: {resp.status}")
                    return
                print("Server is running")
        except aiohttp.ClientError as e:
            print(f"Cannot connect to server: {e}")
            print("Make sure the server is running: python app.py")
            return

        # Get current task status
        async with session.get(f"{base_url}/api/task/status") as resp:
            status = await resp.json()
            print(f"Task status: running={status['running']}")

            if not status['running']:
                print("\nNo task running. Start a task from the web UI first.")
                print("Then run this script to monitor SSE events.")
                return

        # Connect to SSE
        print("\nConnecting to SSE stream...")
        print("Waiting for events (Ctrl+C to stop)...\n")

        try:
            async with session.get(f"{base_url}/api/task/stream") as resp:
                async for line in resp.content:
                    line = line.decode('utf-8').strip()
                    if line:
                        print(f"  {line}")
                    if 'task_complete' in line or 'task_cancelled' in line:
                        print("\nTask completed!")
                        break
        except asyncio.CancelledError:
            print("\nStopped by user")


if __name__ == "__main__":
    try:
        asyncio.run(test_sse())
    except KeyboardInterrupt:
        print("\nStopped")
