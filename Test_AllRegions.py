"""
Quick test for detecting rank and deck name
Run this when the game is on the appropriate screen
"""

from RankDetector import RankDetector

def test_all_regions():
    """Test all configured regions"""
    print("\n" + "="*60)
    print("TESTING ALL CONFIGURED REGIONS")
    print("="*60)
    
    detector = RankDetector()
    
    if not detector.regions:
        print("❌ No regions configured!")
        print("Run SetupRegions.py first.")
        return
    
    print(f"\nConfigured regions: {list(detector.regions.keys())}")
    print("\nMake sure Pokemon TCG Live is visible on screen!")
    input("\nPress Enter to start testing...")
    
    # Test each region
    for region_name in detector.regions.keys():
        print("\n" + "-"*60)
        print(f"Testing region: {region_name}")
        print("-"*60)
        
        if "rank" in region_name.lower():
            # Detect as number
            result = detector.extract_rank(region_name, debug=True)
            if result:
                print(f"✓ Detected: {result}")
            else:
                print(f"✗ No number detected")
                print(f"  Check debug_{region_name}.png")
        else:
            # Detect as text
            result = detector.extract_text(region_name, debug=True)
            if result:
                print(f"✓ Detected: {result}")
            else:
                print(f"✗ No text detected")
                print(f"  Check debug_{region_name}.png")
    
    print("\n" + "="*60)
    print("Testing complete!")
    print("="*60)
    print("\nDebug images saved for each region.")
    print("Review them if detection didn't work as expected.")


if __name__ == "__main__":
    test_all_regions()
